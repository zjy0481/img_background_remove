"""精修逻辑模块（开发文档 4.3 / 4.5）。

负责“涂鸦 → 背景区域推断”与重抠实现；每个精修逻辑在 REFINE_LOGICS 中注册，
前端“精修逻辑选择”下拉框的数据来源于此。
"""

import cv2
import numpy as np
from PIL import Image

from . import matting

REFINE_LOGICS = {
    "smart_region": {
        "name": "智能区域去除",
        "remark": "边缘检测 + 区域分割，整块区域视为背景",
        "description": (
            "对原图进行 Canny 边缘检测，对可通行像素做 8 连通域区域分割；"
            "以涂鸦所在区域为种子，将整块连通区域视为背景并去除，边缘做羽化处理；"
            "弱边缘的极端情况下自动回退为笔画带方案，避免误删整图。"
        ),
        "default": True,
    },
}


def default_logic() -> str:
    """返回默认精修逻辑 ID。"""
    for lid, meta in REFINE_LOGICS.items():
        if meta.get("default"):
            return lid
    return next(iter(REFINE_LOGICS))


def run_refine(logic_id: str, model_id: str, img, strokes: list):
    """按精修逻辑执行重抠，返回 RGBA 图像。"""
    if logic_id not in REFINE_LOGICS:
        raise ValueError(
            f"未知的精修逻辑：{logic_id}（当前支持：{', '.join(REFINE_LOGICS)}）"
        )
    if logic_id == "smart_region":
        return _smart_region_remove(model_id, img, strokes)
    raise ValueError(f"精修逻辑 {logic_id} 尚未实现")


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


def _smart_region_remove(
    model_id: str,
    img,
    strokes: list,
    dilate_px: int = 6,
    canny_low: int = 50,
    canny_high: int = 150,
):
    """智能区域去除（开发文档 4.5）：模型 alpha 为初始值，
    Canny 边缘 + 连通域分割，以涂鸦为种子确定背景区域，整块区域视为背景。
    """
    base = matting.remove_one(model_id, img)  # RGBA
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
