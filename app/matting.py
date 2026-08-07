"""抠图引擎模块。

按开发文档 5.5：模型切换下拉框含 BiRefNet（基础，默认）/ SAM2（进阶）/
ToonOut（动漫角色专用）。
M1 批量引擎接入 rembg（BiRefNet）；SAM2 / ToonOut 的批量接入按里程碑在 M4 实现。
精修逻辑（涂鸦 → 背景区域推断）见 app/refine.py。
"""

import os
import threading
from pathlib import Path

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
