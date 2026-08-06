"use strict";

/* Banner 页面切换（开发文档 3.1 / 3.2） */
const navButtons = document.querySelectorAll(".banner-btn");
const pages = document.querySelectorAll(".page");

function switchPage(name) {
  pages.forEach((p) => p.classList.toggle("active", p.id === "page-" + name));
  navButtons.forEach((b) => b.classList.toggle("active", b.dataset.page === name));
}

navButtons.forEach((btn) =>
  btn.addEventListener("click", () => switchPage(btn.dataset.page))
);

/* 抠图模型下拉框（开发文档 5.5，两页面共享同一设置） */
const modelSelect = document.getElementById("model-select");
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
  } catch (err) {
    console.error("加载模型列表失败：", err);
  }
}

modelSelect.addEventListener("change", (e) => {
  currentModel = e.target.value;
});

/* 服务健康检查 */
async function checkHealth() {
  const el = document.getElementById("statusbar");
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    el.textContent = "服务正常（" + data.stage + " 阶段）";
    el.classList.add("ok");
  } catch (err) {
    el.textContent = "无法连接服务，请确认后端已启动";
  }
}

loadModels();
checkHealth();
