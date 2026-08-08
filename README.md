# 图片背景去除工具（img_background_remove）

本地运行的图片背景去除工具：读取项目根目录 `source_img/` 下的 `.jpg` / `.png` 图片，去除背景后输出到 `processed_img/`（固定 PNG 格式）。支持批量自动去除与人工辅助精修两种模式，界面为中文网页。

首次运行时，工具会自动创建并使用 `source_img/`、`processed_img/`、`temp/` 三个目录。

## 功能说明

顶栏的“抠图模型”下拉框可选择推理模型（当前批量与精修均使用 BiRefNet，SAM2 / ToonOut 将在后续版本接入）。

### 批量模式

- **文件列表**：显示 `source_img/` 中图片的缩略图与文件名，支持手动刷新；
- **选择文件**：多选、全选、全不选（默认全选）；
- **批量处理**：对勾选的图片逐张去除背景（串行执行），实时显示处理进度；结果输出到 `processed_img/`（PNG 格式，文件名为原文件名加 `_no_bg`）；
- **处理结果列表**：显示文件名、缩略图与状态（处理中 / 成功 / 失败），失败项可重新勾选后再次处理；列表支持手动刷新，刷新会重新生成缩略图；
- **大图预览**：点击结果列表中的文件名或缩略图可查看大图，左上角“返回列表”按钮返回，也可按 `Esc` 或点击图片区域外关闭。

### 精修模式

- **选择成品**：从 `processed_img/` 的成品列表（缩略图 + 文件名）中选择一张图片，自动匹配对应的原图；
- **双视图对比**：左侧显示原图并可涂鸦，右侧显示处理结果；两张图缩放与拖动同步；
- **涂鸦工具**：画笔 / 橡皮（共用粗细调节），粗细支持 1–100px 滑块与数字输入双向同步；支持逐笔撤销、一键清空、显示/隐藏涂鸦层；
- **轮次颜色**：不同轮次的涂鸦使用不同颜色，便于区分；
- **提交重抠**：涂鸦区域将被视为背景，结合原图重新抠图，结果保存为轮次文件并显示在右侧结果区；
- **前后对比**：右侧结果区顶部标签栏可切换“精修前 / 精修后”查看效果。
- **多轮涂鸦缓存**：刷新页面或重新打开后，之前的涂鸦与轮次结果会自动恢复，可继续在新轮次上补充涂鸦；
- **回退本轮修改**：可删除最新一轮的涂鸦与结果图，回到本轮修改开始前的状态；
- **保存精修结果**：用最新一轮结果覆盖 `processed_img/` 中的成品，旧版本自动备份；
- **清除缓存 / 清除备份**：清除涂鸦缓存与轮次中间结果（备份保留）；也可删除全部备份（不可恢复）。
- **精修逻辑选择**：可选择精修算法，当前提供“智能区域去除”——基于边缘检测与区域分割，把涂鸦所在的整块连通区域视为背景去除。

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

### 4. GPU 运行所需环境变量（应用已自动设置）

本工具启动时会自动设置以下环境变量（模型目录、numba 缓存目录、CUDA 运行时路径），**通常无需手动执行**。仅在使用独立脚本直接调用 rembg/onnxruntime（不经本应用）、或希望把模型 / 缓存放到自定义位置时，才需要手动设置：

```powershell
$env:PATH = "$env:CONDA_PREFIX\Lib\site-packages\torch\lib;" + $env:PATH
$env:NUMBA_CACHE_DIR = "PROGRAM_PREFIX\temp\numba_cache"
$env:U2NET_HOME = "PROGRAM_PREFIX\temp\models"
```

说明：

- `torch\lib`：为 onnxruntime 提供 CUDA 12 运行时库（如 `cublasLt64_12.dll`）；
- `NUMBA_CACHE_DIR`：避免 numba 缓存写入 site-packages 时被权限拦截，导致程序导入卡死；
- `U2NET_HOME`：模型权重下载目录（首次运行自动下载，约 973MB，之后本地复用）。
- `PROGRAM_PREFIX`：项目根目录的绝对路径

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

## 项目结构

```
app/             # 后端服务（FastAPI）
web/             # 前端页面（中文界面）
requirements.txt # 运行依赖（PyTorch 需按上文单独安装）
README.md
```
