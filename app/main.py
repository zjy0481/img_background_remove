"""M0 骨架入口：启动 FastAPI 服务。

使用方式（均在项目根目录下执行）：
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
  或
  python -m app.main
"""

from .api import app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
