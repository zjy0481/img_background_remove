# 图片背景去除工具（img_background_remove）

本地运行的图片背景去除工具：读取项目根目录 `source_img/` 下的 `.jpg` / `.png` 图片，去除背景后输出到 `processed_img/`（固定 PNG 格式）。支持批量自动去除与人工辅助精修两种模式，界面为中文网页。

首次运行时，工具会自动创建并使用 `source_img/`、`processed_img/`、`temp/` 三个目录。

---

## 环境配置指南（Windows）

### 1. 创建 conda 虚拟环境

```powershell
conda create -n img_bg_rm python=3.12 -y
conda activate img_bg_rm
```

### 2. 安装 PyTorch（CUDA 12 版）

```powershell
conda run -n img_bg_rm pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
```

PyTorch 预编译包自带 CUDA 12.6 运行时，无需单独安装 CUDA Toolkit。

### 3. 安装其余依赖

方式一（逐步安装）：

```powershell
conda run -n img_bg_rm pip install rembg fastapi uvicorn opencv-python
conda run -n img_bg_rm pip install "onnxruntime-gpu==1.26.0"
```

方式二（使用 requirements.txt 一键安装）：

```powershell
conda run -n img_bg_rm pip install -r requirements.txt
```

> 说明：requirements.txt 已包含以上依赖；PyTorch 仍需按第 2 步单独安装。
> 提示：若下载缓慢，可先设置代理（将7890替换为你的实际代理端口）：`$env:HTTP_PROXY='http://127.0.0.1:7890'; $env:HTTPS_PROXY='http://127.0.0.1:7890'`

### 4. 设置 GPU 运行所需环境变量（每次运行前）

```powershell
$env:PATH = "$env:CONDA_PREFIX\Lib\site-packages\torch\lib;" + $env:PATH
$env:NUMBA_CACHE_DIR = "C:\Users\goey8\Desktop\strange tools\img no background\temp\numba_cache"
$env:U2NET_HOME = "C:\Users\goey8\Desktop\strange tools\img no background\temp\models"
```

说明：

- `torch\lib`：为 onnxruntime 提供 CUDA 12 运行时库（如 `cublasLt64_12.dll`）；
- `NUMBA_CACHE_DIR`：避免 numba 缓存写入 site-packages 时被权限拦截，导致程序导入卡死；
- `U2NET_HOME`：模型权重下载目录（首次运行自动下载，约 973MB，之后本地复用）。

### 5. 验证 GPU 是否可用

```powershell
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
python -c "import onnxruntime as ort; print(ort.get_available_providers())"
```

预期输出示例：

```text
True NVIDIA GeForce RTX 4070 Laptop GPU
['TensorrtExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']
```

### 6. 启动服务

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器访问 <http://127.0.0.1:8000>。

> 注意：请使用上面的 `python -m` 方式启动，不要直接运行 `python app/main.py`。

---

## 常见问题

1. **onnxruntime-gpu 报缺 `cublasLt64_13.dll`**：1.27+ 版本按 CUDA 13 构建，本机无 CUDA 13 运行时。请固定使用 `onnxruntime-gpu==1.26.0`，并设置第 4 步的 `torch\lib` PATH。
2. **程序导入卡死（`import rembg` 无响应）**：pymatting 的 numba 编译缓存写入被拦截。设置 `NUMBA_CACHE_DIR` 到项目可写目录后重试。
3. **rembg 安装后提示缺少 onnxruntime**：新版 rembg 将其改为可选依赖，需显式安装 `onnxruntime-gpu`。
4. **并行执行 `conda run` 报“文件被占用”**：conda 临时激活文件互斥，脚本请直接调用环境的 `python.exe`。
5. **控制台中文乱码**：项目文件均为 UTF-8 编码，PowerShell 5.1 以 GBK 显示所致，使用编辑器或浏览器查看正常。

---

## 项目结构（仓库内可见部分）

```
app/             # 后端服务（FastAPI）
web/             # 前端页面（中文界面）
requirements.txt # 运行依赖（PyTorch 需按上文单独安装）
README.md
```
