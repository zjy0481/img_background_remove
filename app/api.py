"""FastAPI 后端骨架（M0）。

按开发文档第 4 节：静态托管 web/ 前端，提供健康检查与模型列表接口；
M1 起在此基础上扩展文件列表、批量处理、精修等 API。
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .matting import MODELS

app = FastAPI(title="图片背景去除工具", version="0.1.0-M0")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@app.get("/api/health")
def health():
    """健康检查接口。"""
    return {"status": "ok", "service": "img_background_remove", "stage": "M0"}


@app.get("/api/models")
def list_models():
    """模型切换下拉框数据源（开发文档 5.5）。"""
    return {
        "models": [
            {"id": mid, "name": m["name"], "remark": m["remark"]}
            for mid, m in MODELS.items()
        ]
    }


app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
