"""抠图引擎模块。

按开发文档 5.5：模型切换下拉框含 BiRefNet（基础，默认）/ SAM2（进阶）/
ToonOut（动漫角色专用）。
M1 批量引擎接入 rembg（BiRefNet）；SAM2 / ToonOut 的批量接入按里程碑在 M4 实现。
"""

import os
import threading
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

MODELS = {
    "birefnet": {"name": "BiRefNet", "remark": "基础", "default": True},
    "sam2": {"name": "SAM2", "remark": "进阶"},
    "toonout": {"name": "ToonOut", "remark": "动漫角色专用"},
}

# M1 可用的 rembg 会话映射
REMBG_SESSION_MAP = {
    "birefnet": "birefnet-general",
}

_session_cache: dict = {}
_session_lock = threading.Lock()


def _bootstrap_environment() -> None:
    """设置关键环境变量（ENVIRONMENT.md 第 4 节），使推理可稳定使用 GPU。"""
    from .storage import MODEL_DIR, NUMBA_CACHE_DIR

    os.environ.setdefault("U2NET_HOME", str(MODEL_DIR))
    os.environ.setdefault("NUMBA_CACHE_DIR", str(NUMBA_CACHE_DIR))
    try:
        import torch

        torch_lib = Path(torch.__file__).resolve().parent / "lib"
        os.environ["PATH"] = str(torch_lib) + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        # torch 缺失时跳过（不影响 CPU 推理）
        pass


_bootstrap_environment()


def default_model() -> str:
    """返回默认模型 ID（BiRefNet）。"""
    for mid, m in MODELS.items():
        if m.get("default"):
            return mid
    return next(iter(MODELS))


def is_supported(model_id: str) -> bool:
    """当前版本（M1）该模型是否可用于批量处理。"""
    return model_id in REMBG_SESSION_MAP


def get_session(model_id: str):
    """获取（并缓存）rembg 会话；仅支持已接入模型。"""
    if model_id not in REMBG_SESSION_MAP:
        raise ValueError(
            f"模型 {model_id} 尚未接入批量处理（当前支持：{', '.join(REMBG_SESSION_MAP)}）"
        )
    with _session_lock:
        if model_id not in _session_cache:
            from rembg import new_session

            _session_cache[model_id] = new_session(
                REMBG_SESSION_MAP[model_id],
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            try:
                print(
                    "[matting] 会话 provider：",
                    _session_cache[model_id].inner_session.get_providers(),
                )
            except Exception:
                pass
        return _session_cache[model_id]


def remove_one(model_id: str, img):
    """对单张 PIL 图像去除背景，返回 RGBA 图像（不重绘前景像素）。"""
    import rembg

    return rembg.remove(img, session=get_session(model_id))


def strokes_to_mask(strokes: list, size: tuple) -> np.ndarray:
    """涂鸦笔画 → 背景蒙版（1=背景种子；橡皮笔画置 0）。坐标基于图像空间。

    采用“点到线段距离”的距离场绘制（纯 numpy），笔画实心、支持橡皮擦除。
    兼容点格式为 [x, y] 或 {"x":.., "y":..}，并对越界坐标做边界钳制。
    """
    w, h = size

    def _point(p):
        if isinstance(p, dict):
            return (float(p.get("x", 0.0)), float(p.get("y", 0.0)))
        return (float(p[0]), float(p[1]))

    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    mask = np.zeros((h, w), dtype=np.uint8)
    for s in strokes:
        raw = s.get("points") or []
        if not raw:
            continue
        width = max(1, int(s.get("width", 8)))
        r = width / 2.0
        pts = [
            (max(0.0, min(float(w), x)), max(0.0, min(float(h), y)))
            for (x, y) in (_point(p) for p in raw)
        ]
        arr = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
        if len(arr) == 1:
            dist = np.hypot(xs - arr[0, 0], ys - arr[0, 1])
        else:
            dist = np.full((h, w), np.inf, dtype=np.float32)
            for i in range(len(arr) - 1):
                p0, p1 = arr[i], arr[i + 1]
                v = p1 - p0
                l2 = float(v[0] * v[0] + v[1] * v[1])
                if l2 < 1e-6:
                    seg = np.hypot(xs - p0[0], ys - p0[1])
                else:
                    t = ((xs - p0[0]) * v[0] + (ys - p0[1]) * v[1]) / l2
                    t = np.clip(t, 0.0, 1.0)
                    proj_x = p0[0] + v[0] * t
                    proj_y = p0[1] + v[1] * t
                    seg = np.hypot(xs - proj_x, ys - proj_y)
                dist = np.minimum(dist, seg)
        inside = dist <= r
        if s.get("eraser"):
            mask[inside] = 0
        else:
            mask[inside] = 255
    return mask


def refine_remove(
    model_id: str,
    img,
    strokes: list,
    dilate_px: int = 6,
    canny_low: int = 50,
    canny_high: int = 150,
):
    """精修重抠（开发文档 3.2.2 / 4.5 方案 A 增强版）。

    流程：模型 alpha 为初始值 → Canny 边缘检测 → 连通域区域分割 →
    以涂鸦为种子确定背景区域 → 整块区域强制视为背景 → 羽化边缘。
    若分割区域几乎覆盖全图且模型认为其中多为前景（边缘缺失的极端情况），
    退回“笔画带”方案，避免误删全图。
    """
    base = remove_one(model_id, img)  # RGBA
    rgba = np.asarray(base.convert("RGBA")).copy()
    alpha = rgba[..., 3].astype(np.float32) / 255.0

    mask = strokes_to_mask(strokes, img.size)
    if not mask.any():
        return base

    gray = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, canny_low, canny_high)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    boundary = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    walkable = cv2.bitwise_not(boundary)

    # 种子轻微膨胀，避免正好落在边缘线上
    seed = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
    n, labels = cv2.connectedComponents(walkable, connectivity=8)
    seed_labels = set(labels[seed > 0].tolist())
    seed_labels.discard(0)
    bg_region = np.zeros_like(mask, np.uint8)
    for lb in seed_labels:
        bg_region[labels == lb] = 255

    # 保护：区域几乎覆盖全图且多为模型前景 → 视为边缘缺失，退回笔画带
    if (bg_region > 0).sum() > 0.95 * mask.size:
        inside = alpha[bg_region > 0]
        if inside.size and float((inside > 0.5).mean()) > 0.5:
            kernel = np.ones((2 * dilate_px + 1, 2 * dilate_px + 1), np.uint8)
            bg_region = cv2.dilate(mask, kernel, iterations=1)

    bg = cv2.GaussianBlur(bg_region.astype(np.float32) / 255.0, (0, 0), sigmaX=dilate_px)
    alpha = alpha * (1.0 - np.clip(bg, 0.0, 1.0))
    rgba[..., 3] = (alpha * 255).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")
