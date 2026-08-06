"""抠图引擎模块（M0 骨架）。

按开发文档 5.5：支持模型切换——BiRefNet（基础，默认）、SAM2（进阶）、
ToonOut（动漫角色专用）。M1 起实现实际会话创建与推理封装
（rembg / onnxruntime CUDA）。
"""

MODELS = {
    "birefnet": {"name": "BiRefNet", "remark": "基础", "default": True},
    "sam2": {"name": "SAM2", "remark": "进阶"},
    "toonout": {"name": "ToonOut", "remark": "动漫角色专用"},
}


def default_model() -> str:
    """返回默认模型 ID。"""
    for mid, m in MODELS.items():
        if m.get("default"):
            return mid
    return next(iter(MODELS))
