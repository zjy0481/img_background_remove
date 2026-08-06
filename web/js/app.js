"use strict";

console.log("[init] 页面脚本已加载");

/* ---------- Banner 页面切换（批量模式 / 精修模式） ---------- */
const navButtons = document.querySelectorAll(".banner-btn");
const pages = document.querySelectorAll(".page");

function switchPage(name) {
  pages.forEach((p) => p.classList.toggle("active", p.id === "page-" + name));
  navButtons.forEach((b) => b.classList.toggle("active", b.dataset.page === name));
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
checkHealth();
