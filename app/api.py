"""FastAPI 后端（M1：批量自动去除背景）。

接口：
- GET  /api/health                健康检查
- GET  /api/models                模型下拉框数据（开发文档 5.5）
- GET  /api/source-files          source_img 文件列表（缩略图 + 文件名）
- GET  /api/processed-files       processed_img 文件列表
- GET  /api/thumbnail             缩略图（kind=source|processed, name=文件名）
- GET  /api/file                  原图 / 成品图（大图预览用）
- POST /api/batch/start           启动批量处理（串行，返回 job_id）
- GET  /api/batch/status/{id}     批量任务状态 / 进度 / 结果
"""

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

from . import matting, refine, storage

app = FastAPI(title="图片背景去除工具", version="0.2.0-M1")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# 确保约定目录存在（开发文档第 2 节）
storage.ensure_dirs()

# v1 并发简化：默认串行（max_workers=1），预留升级接口（开发文档 4.7）
_executor = ThreadPoolExecutor(max_workers=1)
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


class BatchStartRequest(BaseModel):
    files: list[str]
    model: str = "birefnet"


class RefineSubmitRequest(BaseModel):
    name: str  # processed_img 成品文件名（如 cat_no_bg.png）
    strokes: list = []
    model: str = "birefnet"
    logic: str = "smart_region"


def _thumb_url(kind: str, name: str) -> str:
    return f"/api/thumbnail?kind={kind}&name={quote(name)}"


def _file_url(kind: str, name: str) -> str:
    return f"/api/file?kind={kind}&name={quote(name)}"


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "img_background_remove", "stage": "M1"}


@app.get("/api/models")
def list_models():
    return {
        "models": [
            {"id": mid, "name": m["name"], "remark": m["remark"]}
            for mid, m in matting.MODELS.items()
        ]
    }


@app.get("/api/source-files")
def source_files():
    files = [
        {"name": n, "thumb_url": _thumb_url("source", n)}
        for n in storage.source_files()
    ]
    return {"files": files}


@app.get("/api/processed-files")
def processed_files():
    files = [
        {
            "name": n,
            "thumb_url": _thumb_url("processed", n),
            "url": _file_url("processed", n),
        }
        for n in storage.processed_files()
    ]
    return {"files": files}


@app.get("/api/thumbnail")
def thumbnail(kind: str = Query(...), name: str = Query(...)):
    if kind not in ("source", "processed"):
        raise HTTPException(status_code=400, detail="kind 仅支持 source / processed")
    try:
        path = storage.ensure_thumbnail(kind, name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return FileResponse(path, media_type="image/png")


@app.get("/api/file")
def file(kind: str = Query(...), name: str = Query(...)):
    if kind not in ("source", "processed"):
        raise HTTPException(status_code=400, detail="kind 仅支持 source / processed")
    path = storage.source_path_for(name) if kind == "source" else storage.processed_path_for(name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在：{name}")
    media = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(path, media_type=media)


def _batch_worker(job_id: str, files: list[str], model_id: str) -> None:
    with _jobs_lock:
        job = _jobs[job_id]
    for name in files:
        with _jobs_lock:
            job["current"] = name
            job["results"].append(
                {"name": name, "status": "processing", "error": None, "output_name": None}
            )
        output_name = storage.output_name_for(name)
        t_start = time.time()
        try:
            src = storage.source_path_for(name)
            if not src.is_file():
                raise FileNotFoundError(f"源文件不存在：{name}")
            from PIL import Image

            with Image.open(src) as img:
                out = matting.remove_one(model_id, img.convert("RGB"))
            out.save(storage.processed_path_for(output_name), "PNG")
            status = "success"
            error = None
        except Exception as exc:
            status = "failed"
            error = str(exc)
        elapsed = round(time.time() - t_start, 2)
        with _jobs_lock:
            job["results"][-1].update(
                status=status,
                output_name=output_name if status == "success" else None,
                error=error if status == "failed" else None,
                time_seconds=elapsed,
            )
            job["done"] += 1
        print(f"[batch] {name} -> {status} ({elapsed}s)")
    with _jobs_lock:
        job["state"] = "done"
        job["current"] = None


@app.post("/api/batch/start")
def batch_start(req: BatchStartRequest):
    if not req.files:
        raise HTTPException(status_code=400, detail="未选择任何文件")
    if not matting.is_supported(req.model):
        model_name = matting.MODELS.get(req.model, {}).get("name", req.model)
        raise HTTPException(
            status_code=400,
            detail=f"模型 {model_name} 尚未接入批量处理（后续版本实现），当前请使用 BiRefNet",
        )
    valid = [n for n in req.files if storage.source_path_for(n).is_file()]
    if not valid:
        raise HTTPException(status_code=400, detail="所选文件均不存在于 source_img")
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "state": "running",
        "total": len(valid),
        "done": 0,
        "current": None,
        "model": req.model,
        "results": [],
    }
    with _jobs_lock:
        _jobs[job_id] = job
    _executor.submit(_batch_worker, job_id, valid, req.model)
    return {"job_id": job_id, "total": len(valid)}


@app.get("/api/batch/status/{job_id}")
def batch_status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@app.get("/api/refine/match")
def refine_match(name: str = Query(...)):
    """按成品文件名匹配原图（开发文档 3.2.2-2）。"""
    src = storage.match_source_for(name)
    if src is None:
        raise HTTPException(status_code=404, detail="未在 source_img 中匹配到原图")
    return {"name": name, "source": src, "ok": True}


@app.get("/api/refine/logics")
def refine_logics():
    """精修逻辑下拉框数据源（当前仅“智能区域去除”）。"""
    return {
        "logics": [
            {
                "id": lid,
                "name": meta["name"],
                "remark": meta["remark"],
                "description": meta.get("description", ""),
            }
            for lid, meta in refine.REFINE_LOGICS.items()
        ]
    }


@app.post("/api/refine/submit")
def refine_submit(req: RefineSubmitRequest):
    """提交精修：结合涂鸦 + 原图重新抠图，结果存 temp 并返回轮次。"""
    if not matting.is_supported(req.model):
        model_name = matting.MODELS.get(req.model, {}).get("name", req.model)
        raise HTTPException(
            status_code=400,
            detail=f"模型 {model_name} 尚未接入（后续版本实现），当前请使用 BiRefNet",
        )
    proc_path = storage.processed_path_for(req.name)
    if not proc_path.is_file():
        raise HTTPException(status_code=404, detail="成品文件不存在")
    src_name = storage.match_source_for(req.name)
    if src_name is None:
        raise HTTPException(status_code=404, detail="未在 source_img 中匹配到原图")

    try:
        with Image.open(storage.source_path_for(src_name)) as img:
            out = refine.run_refine(req.logic, req.model, img.convert("RGB"), req.strokes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    round_no = storage.next_round(req.name)
    dst = storage.round_path_for(req.name, round_no)
    out.save(dst, "PNG")

    return {
        "round": round_no,
        "url": f"/api/refine/round?name={quote(req.name)}&round={round_no}",
        "prev_url": (
            f"/api/refine/round?name={quote(req.name)}&round={round_no - 1}"
            if round_no > 1
            else _file_url("processed", req.name)
        ),
        "file": str(dst.relative_to(storage.ROOT)).replace("\\", "/"),
    }


@app.get("/api/refine/round")
def refine_round(name: str = Query(...), round: int = Query(...)):
    """读取指定精修轮次结果图。"""
    path = storage.round_path_for(name, round)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="轮次文件不存在")
    return FileResponse(path, media_type="image/png")


app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
