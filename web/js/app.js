"use strict";

console.log("[init] 页面脚本已加载");

/* ---------- Banner 页面切换（批量模式 / 精修模式） ---------- */
const navButtons = document.querySelectorAll(".banner-btn");
const pages = document.querySelectorAll(".page");

function switchPage(name) {
  pages.forEach((p) => p.classList.toggle("active", p.id === "page-" + name));
  navButtons.forEach((b) => b.classList.toggle("active", b.dataset.page === name));
  // 精修页画布初始在隐藏状态下被设成 1×1，切换进入时需重新测量尺寸
  if (name === "refine" && typeof resizeCanvas === "function") {
    resizeCanvas(canvas1, canvasWrap1);
    resizeCanvas(canvas2, canvasWrap2);
    if (refine.imgOriginal) {
      fitView(refine.imgOriginal.naturalWidth, refine.imgOriginal.naturalHeight);
    }
    drawAll();
    console.log("[refine] 进入精修页，画布尺寸：", canvas1.width, "x", canvas1.height, "/", canvas2.width, "x", canvas2.height);
  }
}

navButtons.forEach((btn) =>
  btn.addEventListener("click", () => switchPage(btn.dataset.page))
);

/* ---------- 抠图模型下拉框（两页面共享同一设置） ---------- */
const modelSelect = document.getElementById("model-select");
const modelNotice = document.getElementById("model-notice");
let currentModel = "birefnet";

async function loadModels() {
  try {
    const res = await fetch("/api/models");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    modelSelect.innerHTML = "";
    for (const m of data.models) {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.name + "（" + m.remark + "）";
      if (m.id === currentModel) opt.selected = true;
      modelSelect.appendChild(opt);
    }
    console.log("[models] 已加载模型列表：", data.models.map((m) => m.id).join(", "));
  } catch (err) {
    console.error("[models] 加载模型列表失败：", err);
  }
}

modelSelect.addEventListener("change", (e) => {
  currentModel = e.target.value;
  if (currentModel === "birefnet") {
    modelNotice.hidden = true;
  } else {
    modelNotice.hidden = false;
    modelNotice.textContent = "该模型将在后续版本接入批量处理";
  }
});

/* ---------- 文件列表（source_img） ---------- */
const fileListEl = document.getElementById("file-list");
const fileEmptyEl = document.getElementById("file-empty");
const batchProgressEl = document.getElementById("batch-progress");
const btnRefresh = document.getElementById("btn-refresh");
const btnSelectAll = document.getElementById("btn-select-all");
const btnSelectNone = document.getElementById("btn-select-none");
const btnBatchStart = document.getElementById("btn-batch-start");
const resultListEl = document.getElementById("result-list");
const resultEmptyEl = document.getElementById("result-empty");

let sourceFiles = [];
let batchRunning = false;
const resultItems = new Map();

async function loadSourceFiles() {
  try {
    const res = await fetch("/api/source-files");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    sourceFiles = data.files;
    renderFileList();
    loadProcessedFiles();
    console.log("[files] source_img 文件列表已加载：", sourceFiles.map((f) => f.name).join(", "));
  } catch (err) {
    console.error("[files] 加载文件列表失败：", err);
  }
}

function renderFileList() {
  fileListEl.innerHTML = "";
  fileEmptyEl.hidden = sourceFiles.length > 0;
  for (const f of sourceFiles) {
    const li = document.createElement("li");
    li.className = "file-item";

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "file-check";
    cb.checked = true; // 默认全选
    cb.dataset.name = f.name;

    const img = document.createElement("img");
    img.className = "thumb";
    img.src = f.thumb_url;
    img.alt = f.name;

    const span = document.createElement("span");
    span.className = "file-name";
    span.textContent = f.name;

    li.appendChild(cb);
    li.appendChild(img);
    li.appendChild(span);
    fileListEl.appendChild(li);
  }
}

function checkedNames() {
  return Array.from(fileListEl.querySelectorAll(".file-check:checked")).map(
    (cb) => cb.dataset.name
  );
}

btnRefresh.addEventListener("click", loadSourceFiles);
btnSelectAll.addEventListener("click", () => {
  fileListEl.querySelectorAll(".file-check").forEach((cb) => (cb.checked = true));
  console.log("[select] 已全选，勾选数量：", checkedNames().length);
});
btnSelectNone.addEventListener("click", () => {
  fileListEl.querySelectorAll(".file-check").forEach((cb) => (cb.checked = false));
  console.log("[select] 已全不选");
});

/* ---------- 批量处理（串行 + 进度） ---------- */
async function startBatch() {
  if (batchRunning) return;
  const files = checkedNames();
  console.log("[batch] 开始批量处理，文件：", files.join(", "), "| 模型：", currentModel);
  if (files.length === 0) {
    alert("请先勾选要处理的文件");
    return;
  }
  if (currentModel !== "birefnet") {
    alert("当前模型尚未接入批量处理，请先切换为 BiRefNet");
    return;
  }
  batchRunning = true;
  btnBatchStart.disabled = true;
  batchProgressEl.hidden = false;
  batchProgressEl.textContent = "正在启动…";
  try {
    const res = await fetch("/api/batch/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files: files, model: currentModel }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "HTTP " + res.status);
    }
    const data = await res.json();
    console.log("[batch] 任务已创建 job_id=", data.job_id, "total=", data.total);
    await pollBatch(data.job_id);
  } catch (err) {
    console.error("[batch] 批量处理启动失败：", err);
    alert("批量处理失败：" + err.message);
    batchProgressEl.textContent = "";
    batchProgressEl.hidden = true;
  } finally {
    batchRunning = false;
    btnBatchStart.disabled = false;
    loadProcessedFiles();
  }
}

btnBatchStart.addEventListener("click", startBatch);

async function pollBatch(jobId) {
  for (;;) {
    const res = await fetch("/api/batch/status/" + jobId);
    if (!res.ok) {
      console.error("[batch] 查询任务状态失败，HTTP", res.status);
      throw new Error("查询任务状态失败");
    }
    const job = await res.json();
    console.log(
      "[batch] 进度", job.done + "/" + job.total,
      "| 当前：", job.current || "-",
      "| 状态：", job.state
    );
    batchProgressEl.textContent =
      "进度：" +
      job.done +
      "/" +
      job.total +
      (job.current ? "（正在处理：" + job.current + "）" : "");
    if (job.state === "done") {
      batchProgressEl.textContent += " —— 处理完成";
      renderResults(job.results);
      console.log("[batch] 任务完成：", job.results.map((r) => r.name + "=" + r.status).join(", "));
      return;
    }
    await new Promise((r) => setTimeout(r, 800));
  }
}

/* ---------- 处理结果列表 + 大图预览 ---------- */
function statusText(status) {
  if (status === "processing") return "处理中";
  if (status === "success") return "成功";
  return "失败";
}

function renderResults(results) {
  for (const r of results) {
    const key = resultKey(r);
    let li = resultItems.get(key);
    if (!li) {
      li = document.createElement("li");
      li.className = "result-item";
      resultItems.set(key, li);
      resultListEl.appendChild(li);
    }
    updateResultItem(li, r, key);
  }
  console.log("[results] 已渲染结果：", results.map((r) => resultKey(r) + "=" + r.status).join(", "));
  resultEmptyEl.hidden = resultListEl.children.length > 0;
}

function resultKey(r) {
  /* 以输出文件名为唯一标识：成功项用 xxx_no_bg.png，失败项退回源文件名 */
  return r.output_name || r.name;
}

function updateResultItem(li, r, key) {
  li.innerHTML = "";
  const displayName = r.output_name || r.name;

  const img = document.createElement("img");
  img.className = "thumb";
  img.alt = displayName;
  const thumbName = r.output_name || r.name;
  if (r.status === "success") {
    img.src = "/api/thumbnail?kind=processed&name=" + encodeURIComponent(thumbName);
  }

  const span = document.createElement("span");
  span.className = "file-name";
  span.textContent = displayName;

  const badge = document.createElement("span");
  badge.className = "badge badge-" + r.status;
  badge.textContent = statusText(r.status);

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "preview-btn";
  btn.textContent = "查看大图";
  btn.disabled = r.status !== "success"; // 仅成品可预览
  btn.addEventListener("click", () => openPreview(thumbName));

  li.appendChild(img);
  li.appendChild(span);
  li.appendChild(badge);
  li.appendChild(btn);
}

async function loadProcessedFiles() {
  try {
    const res = await fetch("/api/processed-files");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    renderResults(
      data.files.map((f) => ({ name: f.name, status: "success", output_name: f.name }))
    );
  } catch (err) {
    console.error("[results] 加载处理结果失败：", err);
  }
}

/* ---------- 大图预览层（模态） ---------- */
const previewModal = document.getElementById("preview-modal");
const previewImg = document.getElementById("preview-img");
const previewBack = document.getElementById("preview-back");

function openPreview(name) {
  const url = "/api/file?kind=processed&name=" + encodeURIComponent(name);
  previewImg.src = url;
  previewModal.hidden = false;
  previewModal.style.display = "flex";
  console.log("[preview] 打开大图预览：", name, "->", url);
}

function closePreview() {
  console.log("[preview] 关闭大图预览");
  previewModal.hidden = true;
  previewModal.style.display = "none";
  previewImg.src = "";
}

previewBack.addEventListener("click", closePreview);
previewModal.addEventListener("click", (e) => {
  if (e.target === previewModal) closePreview();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closePreview();
});

/* ================= M2：人工辅助精修 ================= */
const refineFileList = document.getElementById("refine-file-list");
const refineFileEmpty = document.getElementById("refine-file-empty");
const refineHint = document.getElementById("refine-hint");
const btnRefineRefresh = document.getElementById("btn-refine-refresh");
const canvasWrap1 = document.getElementById("canvas-wrap1");
const canvasWrap2 = document.getElementById("canvas-wrap2");
const canvas1 = document.getElementById("canvas1");
const canvas2 = document.getElementById("canvas2");
const btnBrush = document.getElementById("btn-brush");
const btnEraser = document.getElementById("btn-eraser");
const brushSize = document.getElementById("brush-size");
const brushSizeNum = document.getElementById("brush-size-num");
const btnUndo = document.getElementById("btn-undo");
const btnClear = document.getElementById("btn-clear");
const btnToggleStrokes = document.getElementById("btn-toggle-strokes");
const roundLabel = document.getElementById("round-label");
const btnSubmit = document.getElementById("btn-submit");
const refineProgress = document.getElementById("refine-progress");
const tabPrev = document.getElementById("tab-prev");
const tabNext = document.getElementById("tab-next");

const ROUND_COLORS = ["#ff3b30", "#007aff", "#34c759", "#ff9500", "#af52de", "#ff2d55"];
const refine = {
  processedName: null,
  sourceName: null,
  round: 0, // 已完成轮次（0 = 仅批量自动结果）
  strokes: [], // 累积笔画（跨轮次保留，开发文档 3.2.2-6）
  tool: "brush",
  brushWidth: 12,
  showStrokes: true,
  tab: "prev",
  imgOriginal: null,
  imgPrev: null,
  imgNext: null,
  view: { scale: 1, ox: 0, oy: 0 },
  painting: false,
  panning: false,
  currentStroke: null,
  lastX: 0,
  lastY: 0,
  ctx1: null,
  ctx2: null,
  dpr: window.devicePixelRatio || 1,
};

// 离屏涂鸦图层：橡皮用 destination-out 只擦涂鸦，不碰原图
const strokeLayer = document.createElement("canvas");

function resizeCanvas(cv, wrap) {
  const rect = wrap.getBoundingClientRect();
  cv.width = Math.max(1, Math.floor(rect.width * refine.dpr));
  cv.height = Math.max(1, Math.floor(rect.height * refine.dpr));
  cv.style.width = rect.width + "px";
  cv.style.height = rect.height + "px";
  if (cv === canvas1) {
    strokeLayer.width = cv.width;
    strokeLayer.height = cv.height;
  }
}

function setupCanvases() {
  refine.ctx1 = canvas1.getContext("2d");
  refine.ctx2 = canvas2.getContext("2d");
  resizeCanvas(canvas1, canvasWrap1);
  resizeCanvas(canvas2, canvasWrap2);
  drawAll();
}

function fitView(imgW, imgH) {
  const w = canvas1.width / refine.dpr;
  const h = canvas1.height / refine.dpr;
  const scale = Math.min(w / imgW, h / imgH, 1) * 0.92;
  refine.view = { scale: scale || 1, ox: (w - imgW * scale) / 2, oy: (h - imgH * scale) / 2 };
}

function toImagePoint(clientX, clientY) {
  const rect = canvas1.getBoundingClientRect();
  return {
    x: (clientX - rect.left - refine.view.ox) / refine.view.scale,
    y: (clientY - rect.top - refine.view.oy) / refine.view.scale,
  };
}

function clampToImage(p) {
  if (!refine.imgOriginal) return p;
  const w = refine.imgOriginal.naturalWidth;
  const h = refine.imgOriginal.naturalHeight;
  return {
    x: Math.max(0, Math.min(w, p.x)),
    y: Math.max(0, Math.min(h, p.y)),
  };
}

function drawImage(ctx, cv, img) {
  const v = refine.view;
  const w = cv.width / refine.dpr;
  const h = cv.height / refine.dpr;
  ctx.save();
  ctx.scale(refine.dpr, refine.dpr);
  ctx.clearRect(0, 0, w, h);
  ctx.translate(v.ox, v.oy);
  ctx.scale(v.scale, v.scale);
  if (img) ctx.drawImage(img, 0, 0);
  ctx.restore();
}

function drawStrokes(ctx, cv) {
  if (!refine.showStrokes) return;
  const sctx = strokeLayer.getContext("2d");
  const v = refine.view;
  sctx.clearRect(0, 0, strokeLayer.width, strokeLayer.height);
  sctx.save();
  sctx.scale(refine.dpr, refine.dpr);
  sctx.translate(v.ox, v.oy);
  sctx.scale(v.scale, v.scale);
  // 涂鸦裁剪到图片矩形，超出图片边界的部分不显示
  if (refine.imgOriginal) {
    sctx.save();
    sctx.beginPath();
    sctx.rect(0, 0, refine.imgOriginal.naturalWidth, refine.imgOriginal.naturalHeight);
    sctx.clip();
  }
  // 已完成的笔画 + 正在绘制的笔画（实时渲染）
  const all = refine.strokes.concat(refine.currentStroke ? [refine.currentStroke] : []);
  for (const s of all) {
    if (!s.points || s.points.length === 0) continue;
    // 橡皮：destination-out 只擦除涂鸦层已有内容（含之前轮次），不会覆盖原图
    sctx.globalCompositeOperation = s.eraser ? "destination-out" : "source-over";
    sctx.strokeStyle = s.color;
    sctx.lineWidth = Math.max(1, s.width);
    sctx.lineCap = "round";
    sctx.lineJoin = "round";
    sctx.beginPath();
    s.points.forEach((p, i) => (i === 0 ? sctx.moveTo(p.x, p.y) : sctx.lineTo(p.x, p.y)));
    if (s.points.length === 1) {
      sctx.lineTo(s.points[0].x + 0.01, s.points[0].y + 0.01);
    }
    sctx.stroke();
  }
  sctx.globalCompositeOperation = "source-over";
  if (refine.imgOriginal) sctx.restore();
  sctx.restore();
  // 涂鸦层叠加到画布（橡皮区域已透明，原图正常透出）
  ctx.drawImage(strokeLayer, 0, 0);
}

function drawAll() {
  drawImage(refine.ctx1, canvas1, refine.imgOriginal);
  drawStrokes(refine.ctx1, canvas1);
  const img2 = refine.tab === "next" && refine.imgNext ? refine.imgNext : refine.imgPrev;
  drawImage(refine.ctx2, canvas2, img2);
}

function updateTabUI() {
  tabPrev.classList.toggle("active", refine.tab === "prev");
  tabNext.classList.toggle("active", refine.tab === "next");
  tabNext.disabled = !refine.imgNext;
}

function updateRoundLabel() {
  const idx = refine.round % ROUND_COLORS.length;
  roundLabel.textContent = "第 " + (refine.round + 1) + " 轮涂鸦";
  roundLabel.style.color = ROUND_COLORS[idx];
}

function setTool(tool) {
  refine.tool = tool;
  btnBrush.classList.toggle("active", tool === "brush");
  btnEraser.classList.toggle("active", tool === "eraser");
}

function loadRefineImage(store, key, url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      store[key] = img;
      resolve();
    };
    img.onerror = () => reject(new Error("图片加载失败：" + url));
    img.src = url;
  });
}

async function loadRefineFiles() {
  try {
    const res = await fetch("/api/processed-files");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    renderRefineFiles(data.files);
    console.log("[refine] 成品列表已加载：", data.files.map((f) => f.name).join(", "));
  } catch (err) {
    console.error("[refine] 加载成品列表失败：", err);
  }
}

function renderRefineFiles(files) {
  refineFileList.innerHTML = "";
  refineFileEmpty.hidden = files.length > 0;
  for (const f of files) {
    const li = document.createElement("li");
    li.className = "result-item";
    li.dataset.name = f.name;
    if (f.name === refine.processedName) li.classList.add("selected");
    const img = document.createElement("img");
    img.className = "thumb";
    img.src = f.thumb_url;
    img.alt = f.name;
    const span = document.createElement("span");
    span.className = "file-name";
    span.textContent = f.name;
    li.appendChild(img);
    li.appendChild(span);
    li.addEventListener("click", () => selectRefineItem(f.name));
    refineFileList.appendChild(li);
  }
}

async function selectRefineItem(name) {
  try {
    const res = await fetch("/api/refine/match?name=" + encodeURIComponent(name));
    if (!res.ok) {
      const e = await res.json();
      throw new Error(e.detail || "匹配失败");
    }
    const data = await res.json();
    refine.processedName = name;
    refine.sourceName = data.source;
    refine.round = 0;
    refine.strokes = [];
    refine.imgNext = null;
    refine.tab = "prev";
    updateTabUI();
    await loadRefineImage(refine, "imgOriginal", "/api/file?kind=source&name=" + encodeURIComponent(data.source));
    await loadRefineImage(refine, "imgPrev", "/api/file?kind=processed&name=" + encodeURIComponent(name));
    fitView(refine.imgOriginal.naturalWidth, refine.imgOriginal.naturalHeight);
    btnSubmit.disabled = false;
    refineHint.textContent = "已选择：" + name + "（原图 " + data.source + "）";
    updateRoundLabel();
    drawAll();
    document.querySelectorAll("#refine-file-list .result-item").forEach((li) => {
      li.classList.toggle("selected", li.dataset.name === name);
    });
    console.log("[refine] 已选择成品：", name, "| 原图：", data.source);
  } catch (err) {
    alert("选择失败：" + err.message);
  }
}

async function submitRefine() {
  if (!refine.processedName) return;
  if (refine.strokes.length === 0) {
    alert("请先在图槽 1 涂鸦标记要视为背景的区域");
    return;
  }
  btnSubmit.disabled = true;
  refineProgress.hidden = false;
  refineProgress.textContent = "正在重抠（首次较慢，请稍候）…";
  try {
    const res = await fetch("/api/refine/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: refine.processedName,
        strokes: refine.strokes,
        model: currentModel,
      }),
    });
    if (!res.ok) {
      const e = await res.json();
      throw new Error(e.detail || "HTTP " + res.status);
    }
    const data = await res.json();
    refine.round = data.round;
    await loadRefineImage(refine, "imgPrev", data.prev_url);
    await loadRefineImage(refine, "imgNext", data.url);
    refine.tab = "next";
    updateTabUI();
    refineProgress.textContent = "第 " + data.round + " 轮精修完成";
    updateRoundLabel();
    drawAll();
    console.log("[refine] 提交成功：", data);
  } catch (err) {
    console.error("[refine] 提交失败：", err);
    alert("精修失败：" + err.message);
  } finally {
    btnSubmit.disabled = false;
  }
}

function attachCanvasEvents(cv, isSlot1) {
  // 两个图槽共享同一视口：在任意图槽上平移/缩放都会双向同步
  cv.addEventListener("contextmenu", (e) => e.preventDefault());
  cv.addEventListener("mousedown", (e) => {
    if (e.button === 1) {
      // 中键平移（右键与浏览器菜单冲突，不使用）
      refine.panning = true;
      refine.lastX = e.clientX;
      refine.lastY = e.clientY;
      e.preventDefault();
    } else if (e.button === 0) {
      if (isSlot1) {
        refine.painting = true;
        const p = clampToImage(toImagePoint(e.clientX, e.clientY));
        refine.currentStroke = {
          points: [p],
          width: refine.brushWidth,
          round: refine.round + 1,
          color: ROUND_COLORS[refine.round % ROUND_COLORS.length],
          eraser: refine.tool === "eraser",
        };
      } else {
        // 结果区左键拖动 = 平移
        refine.panning = true;
        refine.lastX = e.clientX;
        refine.lastY = e.clientY;
      }
    }
  });
  cv.addEventListener("mousemove", (e) => {
    if (refine.painting && refine.currentStroke) {
      refine.currentStroke.points.push(clampToImage(toImagePoint(e.clientX, e.clientY)));
      drawAll(); // 实时渲染涂鸦痕迹
    } else if (refine.panning) {
      refine.view.ox += e.clientX - refine.lastX;
      refine.view.oy += e.clientY - refine.lastY;
      refine.lastX = e.clientX;
      refine.lastY = e.clientY;
      drawAll();
    }
  });
  const end = () => {
    if (refine.painting && refine.currentStroke && refine.currentStroke.points.length) {
      refine.strokes.push(refine.currentStroke);
    }
    refine.painting = false;
    refine.panning = false;
    refine.currentStroke = null;
    drawAll();
  };
  cv.addEventListener("mouseup", end);
  cv.addEventListener("mouseleave", end);
  cv.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      const rect = cv.getBoundingClientRect();
      const cx = e.clientX - rect.left;
      const cy = e.clientY - rect.top;
      const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
      const ns = Math.min(20, Math.max(0.05, refine.view.scale * factor));
      refine.view.ox = cx - ((cx - refine.view.ox) / refine.view.scale) * ns;
      refine.view.oy = cy - ((cy - refine.view.oy) / refine.view.scale) * ns;
      refine.view.scale = ns;
      drawAll();
    },
    { passive: false }
  );
}

function bindRefineEvents() {
  btnBrush.addEventListener("click", () => setTool("brush"));
  btnEraser.addEventListener("click", () => setTool("eraser"));
  btnUndo.addEventListener("click", () => {
    refine.strokes.pop();
    drawAll();
  });
  btnClear.addEventListener("click", () => {
    refine.strokes = [];
    drawAll();
  });
  btnToggleStrokes.addEventListener("click", () => {
    refine.showStrokes = !refine.showStrokes;
    drawAll();
  });
  btnRefineRefresh.addEventListener("click", loadRefineFiles);
  btnSubmit.addEventListener("click", submitRefine);

  brushSize.addEventListener("input", () => {
    brushSizeNum.value = brushSize.value;
    refine.brushWidth = Number(brushSize.value);
  });
  brushSizeNum.addEventListener("input", () => {
    let v = Number(brushSizeNum.value);
    if (Number.isNaN(v) || v < 1) v = 1;
    if (v > 100) v = 100;
    brushSizeNum.value = v;
    brushSize.value = v;
    refine.brushWidth = v;
  });

  tabPrev.addEventListener("click", () => {
    refine.tab = "prev";
    updateTabUI();
    drawAll();
  });
  tabNext.addEventListener("click", () => {
    if (refine.imgNext) {
      refine.tab = "next";
      updateTabUI();
      drawAll();
    }
  });

  attachCanvasEvents(canvas1, true);
  attachCanvasEvents(canvas2, false);
}

function initRefine() {
  setupCanvases();
  bindRefineEvents();
  updateTabUI();
  loadRefineFiles();
}

/* ---------- 服务健康检查 ---------- */
async function checkHealth() {
  const el = document.getElementById("statusbar");
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    el.textContent = "服务正常";
    el.classList.add("ok");
    console.log("[health] 服务正常：", data.stage);
  } catch (err) {
    el.textContent = "无法连接服务，请确认后端已启动";
    console.error("[health] 无法连接服务：", err);
  }
}

/* ---------- 初始化 ---------- */
loadModels();
loadSourceFiles();
initRefine();
checkHealth();
