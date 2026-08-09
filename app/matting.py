"""抠图引擎模块。

按开发文档 5.5：模型切换下拉框含 BiRefNet（基础，默认）/ ToonOut（动漫角色专用）。
SAM2 因批量自动掩码策略效果差（复杂图 95% 背景误判）已暂从项目移除（见 M4 文档第 9 节），
改进策略见 M4 文档第 8 节，待实施后重新接入。

精修逻辑（涂鸦 → 背景区域推断）见 app/refine.py。
"""

import os
import sys
import threading
from pathlib import Path

import numpy as np
from PIL import Image

from .storage import MODEL_DIR, NUMBA_CACHE_DIR

MODELS = {
    "birefnet": {"name": "BiRefNet", "remark": "基础", "default": True},
    "toonout": {"name": "ToonOut", "remark": "动漫角色专用"},
}

# 模型 → 引擎类型
MODEL_KIND = {
    "birefnet": "rembg",
    "toonout": "toonout",
}

# rembg 会话映射（仅 BiRefNet 使用 rembg）
REMBG_SESSION_MAP = {
    "birefnet": "birefnet-general",
}

TOONOUT_RUNTIME_DIR = MODEL_DIR / "toonout_runtime"
TOONOUT_CKPT = MODEL_DIR / "birefnet_finetuned_toonout.pth"

_session_cache: dict = {}
_session_lock = threading.Lock()


def _bootstrap_environment() -> None:
    """设置关键环境变量（ENVIRONMENT.md 第 4 节），使推理可稳定使用 GPU。"""
    os.environ.setdefault("U2NET_HOME", str(MODEL_DIR))
    os.environ.setdefault("NUMBA_CACHE_DIR", str(NUMBA_CACHE_DIR))
    try:
        import torch

        torch_lib = Path(torch.__file__).resolve().parent / "lib"
        os.environ["PATH"] = str(torch_lib) + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


_bootstrap_environment()


def default_model() -> str:
    """返回默认模型 ID（BiRefNet）。"""
    for mid, m in MODELS.items():
        if m.get("default"):
            return mid
    return next(iter(MODELS))


def is_supported(model_id: str) -> bool:
    """该模型当前是否可用于批量/精修。"""
    return model_id in MODELS


def get_session(model_id: str):
    """获取（并缓存）rembg 会话；仅 BiRefNet 使用。"""
    if model_id not in REMBG_SESSION_MAP:
        raise ValueError(
            f"模型 {model_id} 不使用 rembg 会话（当前支持：{', '.join(REMBG_SESSION_MAP)}）"
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
    """按模型分派去除背景，返回 RGBA 图像（不重绘前景像素）。"""
    kind = MODEL_KIND.get(model_id)
    if kind is None:
        raise ValueError(f"未知模型：{model_id}")
    if kind == "rembg":
        import rembg

        return rembg.remove(img, session=get_session(model_id))
    if kind == "toonout":
        return _toonout_remove(img)
    raise ValueError(f"模型 {model_id} 尚未接入推理引擎")


# ---------------- ToonOut（动漫角色专用） ----------------


def _load_toonout():
    """加载并缓存 ToonOut torch 模型（BiRefNet + 微调权重，512 输入）。"""
    with _session_lock:
        if "toonout" in _session_cache:
            return _session_cache["toonout"]
        if not TOONOUT_RUNTIME_DIR.is_dir():
            raise FileNotFoundError(
                f"缺少 ToonOut 运行时目录：{TOONOUT_RUNTIME_DIR}"
            )
        if str(TOONOUT_RUNTIME_DIR) not in sys.path:
            sys.path.insert(0, str(TOONOUT_RUNTIME_DIR))
        import torch
        from birefnet.models.birefnet import BiRefNet

        model = BiRefNet(bb_pretrained=False)
        sd = torch.load(TOONOUT_CKPT, map_location="cpu")
        clean = {}
        for k, v in sd.items():
            for pre in ("module._orig_mod.", "module."):
                if k.startswith(pre):
                    k = k[len(pre):]
                    break
            clean[k] = v
        model.load_state_dict(clean)
        model.eval().cuda()
        _session_cache["toonout"] = model
        return model


def _toonout_remove(img):
    """ToonOut 去背景：torch 前向（512 输入）→ sigmoid → 归一化蒙版 → 合成 RGBA。"""
    model = _load_toonout()
    import torch

    size = (512, 512)
    im = img.convert("RGB").resize(size, Image.Resampling.LANCZOS)
    arr = np.asarray(im).astype(np.float32) / 255.0
    arr = (arr - np.array([0.485, 0.456, 0.406], np.float32)) / np.array(
        [0.229, 0.224, 0.225], np.float32
    )
    x = torch.from_numpy(arr.transpose(2, 0, 1)[None]).cuda()
    with torch.no_grad():
        out = model(x)[-1]
    pred = torch.sigmoid(out).float().cpu().numpy()[0, 0]
    pred = (pred - pred.min()) / (pred.max() - pred.min() + 1e-8)
    mask = Image.fromarray((pred * 255).astype(np.uint8), mode="L").resize(
        img.size, Image.Resampling.LANCZOS
    )
    rgba = img.convert("RGBA")
    rgba.putalpha(mask)
    return rgba
