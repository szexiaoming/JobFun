"use strict";

// This public demo is intentionally self-contained and uses synthetic examples.
const examples = {
  fastapi: {
    title: "FastAPI 后端开发",
    status: "proven",
    statusLabel: "有明确证据",
    explanation: "示例简历明确写到使用 FastAPI 搭建服务接口。该原文支持这项技术要求；具体项目范围仍应由候选人核对。",
    evidence: "使用 FastAPI 搭建服务接口并实现鉴权。",
    sourceId: "source-fastapi",
    question: "你能说明这段示例经历中，接口设计和鉴权分别由谁负责吗？",
    action: "围绕有原文支持的工作准备项目背景、个人贡献与技术权衡。"
  },
  async: {
    title: "高并发异步任务治理",
    status: "partial",
    statusLabel: "部分相关",
    explanation: "示例简历写到了任务排队、状态跟踪和失败重试，但没有描述并发规模或稳定性验证。因此只能判断为部分相关。",
    evidence: "实现异步任务排队、状态跟踪与失败重试。",
    sourceId: "source-async",
    question: "你是否做过并发压测、容量规划或故障演练？如果有，能找到对应记录吗？",
    action: "先核实实际处理规模和验证方法；只有存在真实依据时才补充到简历。"
  },
  kubernetes: {
    title: "Kubernetes 部署实践",
    status: "missing",
    statusLabel: "当前版本未找到证据",
    explanation: "这份示例简历没有提到 Kubernetes 或容器编排实践，因此不能声称满足这项加分要求。",
    evidence: "",
    sourceId: "",
    question: "你是否有尚未写入简历、且能够举证的 Kubernetes 实践？",
    action: "如果没有真实经历，可把它列为学习方向；不要把计划中的学习写成已完成项目。"
  }
};

const buttons = [...document.querySelectorAll(".requirement-button")];
const analyzeButton = document.getElementById("analyze-button");
const output = document.getElementById("explanation-output");
let selectedKey = "fastapi";
let pendingTimer = null;

buttons.forEach((button) => {
  button.addEventListener("click", () => {
    const key = button.dataset.key;
    if (!Object.hasOwn(examples, key)) return;
    selectedKey = key;
    buttons.forEach((item) => {
      const active = item === button;
      item.classList.toggle("is-selected", active);
      item.setAttribute("aria-pressed", String(active));
    });
    if (pendingTimer !== null) window.clearTimeout(pendingTimer);
    pendingTimer = null;
    analyzeButton.disabled = false;
    analyzeButton.textContent = "解释这项差距";
    output.className = "explanation-empty";
    output.replaceChildren(
      element("span", "empty-symbol", "◎"),
      element("strong", "", "已选择：" + examples[key].title),
      element("p", "", "点击按钮，查看这项要求与示例简历的证据关系。")
    );
  });
});

analyzeButton.addEventListener("click", () => {
  if (pendingTimer !== null) window.clearTimeout(pendingTimer);
  const key = selectedKey;
  analyzeButton.disabled = true;
  analyzeButton.textContent = "正在核对示例证据…";
  output.className = "loading";
  output.replaceChildren(element("span", "spinner", ""), element("span", "", "正在读取岗位要求与简历原文…"));
  pendingTimer = window.setTimeout(() => {
    pendingTimer = null;
    renderResult(examples[key]);
    analyzeButton.disabled = false;
    analyzeButton.textContent = "重新解释这项差距";
  }, 650);
});

function renderResult(example) {
  const result = element("div", "result");
  const titleRow = element("div", "result-title-row");
  titleRow.append(element("h4", "", example.title), element("span", "result-pill " + example.status, example.statusLabel));
  result.append(titleRow, element("p", "result-lead", example.explanation));

  const evidence = block("简历证据", example.evidence || "当前示例简历中没有可引用的原文。", "evidence");
  if (example.sourceId) {
    const link = element("a", "source-link", "查看简历原文");
    link.href = "#" + example.sourceId;
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const source = document.getElementById(example.sourceId);
      if (!source) return;
      window.history.replaceState(null, "", "#" + example.sourceId);
      source.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "center" });
      source.classList.add("is-highlighted");
      window.setTimeout(() => source.classList.remove("is-highlighted"), 3000);
    });
    evidence.append(link);
  }
  result.append(evidence, block("需要你确认", example.question), block("下一步行动", example.action));
  result.append(element("small", "result-note", "演示结果由固定示例生成；真实产品使用服务端证据校验与可选 LangChain 工具。"));
  output.className = "";
  output.replaceChildren(result);
}

function block(title, description, extraClass = "") {
  const container = element("section", "result-block " + extraClass);
  container.append(element("h5", "", title), element("p", "", description));
  return container;
}

function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = content;
  return node;
}
