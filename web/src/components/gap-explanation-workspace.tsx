"use client";

import { useEffect, useState } from "react";

import type { GapExplanation, GapEvidence, GapRequirement, Operation } from "@/lib/client-api-types";

const statusLabels: Record<GapRequirement["status"], string> = {
  proven: "有明确证据", partial: "部分相关", missing: "未找到证据",
  uncertain: "待确认", unassessed: "尚未逐条评估",
};

async function readResponse<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null) as T | { error?: string | { message?: string } } | null;
  if (!response.ok) {
    const error = body && typeof body === "object" && "error" in body ? body.error : null;
    throw new Error(typeof error === "string" ? error : error?.message || "请求未能完成，请稍后重试");
  }
  return body as T;
}

export function GapExplanationWorkspace({ applicationId, requirements }: { applicationId: number; requirements: GapRequirement[] }) {
  const [selectedKey, setSelectedKey] = useState(requirements[0]?.key || "");
  const [operation, setOperation] = useState<Operation | null>(null);
  const [explanation, setExplanation] = useState<GapExplanation | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const selected = requirements.find((item) => item.key === selectedKey);

  useEffect(() => {
    if (!operation || ["succeeded", "failed"].includes(operation.status)) return;
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`/api/backend/operations/${operation.id}`, { cache: "no-store" });
        const next = await readResponse<Operation>(response);
        if (!cancelled) setOperation(next);
      } catch (requestError) {
        if (!cancelled) setError(requestError instanceof Error ? requestError.message : "无法刷新任务进度");
      }
    }, 1200);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [operation]);

  useEffect(() => {
    if (!operation || operation.status !== "succeeded") return;
    let cancelled = false;
    async function loadResult() {
      try {
        const response = await fetch(`/api/backend/gap-explanations/${operation?.id}`, { cache: "no-store" });
        const result = await readResponse<GapExplanation>(response);
        if (!cancelled) setExplanation(result);
      } catch (requestError) {
        if (!cancelled) setError(requestError instanceof Error ? requestError.message : "解释结果读取失败");
      }
    }
    void loadResult();
    return () => { cancelled = true; };
  }, [operation]);

  async function submit() {
    if (!selected) return;
    setSubmitting(true);
    setError("");
    setOperation(null);
    setExplanation(null);
    try {
      const response = await fetch(`/api/backend/applications/${applicationId}/gap-explanations`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": `web-gap-${crypto.randomUUID()}`,
        },
        body: JSON.stringify({ requirement_key: selected.key }),
      });
      setOperation(await readResponse<Operation>(response));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "解释任务提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  const busy = submitting || (operation != null && !["succeeded", "failed"].includes(operation.status));

  return <section className="detailPanel gapWorkspace" aria-labelledby="gap-title">
    <div className="panelHeading"><div><p className="eyebrow">岗位差距解释助手</p><h2 id="gap-title">逐项查看要求与证据</h2></div><span className="stateBadge">只读分析</span></div>
    <p className="panelHint">解释只使用这份申请绑定的岗位与简历版本。候选段落需要你核实，解释不会修改简历或申请状态。</p>
    {!requirements.length ? <p className="panelHint">当前岗位没有可拆分的要求，请检查岗位资料。</p> : <>
      <div className="fieldGroup"><label htmlFor="gap-requirement">选择岗位要求</label><span className="selectField"><select id="gap-requirement" value={selectedKey} onChange={(event) => { setSelectedKey(event.target.value); setOperation(null); setExplanation(null); setError(""); }}>{requirements.map((item) => <option key={item.key} value={item.key}>{item.text}</option>)}</select></span></div>
      {selected ? <div className="gapSelected"><strong>{selected.text}</strong><span className="stateBadge">{statusLabels[selected.status]}</span>{selected.evidence.length ? <EvidenceList title="已保存的证据" items={selected.evidence} /> : <p>当前没有可展示的已验证证据。</p>}</div> : null}
      <button className="primaryButton compact" type="button" disabled={busy} onClick={() => void submit()}>{submitting ? "正在提交…" : busy ? "正在分析…" : "解释这项差距"}</button>
      {operation ? <p className="panelHint" aria-live="polite">{operation.status === "queued" ? "等待分析" : operation.status === "running" ? "正在核对证据" : operation.status === "succeeded" ? "解释已完成" : "解释失败"} · 任务 #{operation.id} · {operation.progress}%</p> : null}
      {error ? <p className="formError" role="alert">{error}</p> : null}
      {operation?.status === "failed" ? <p className="formError" role="alert">{operation.error_message || "解释任务未完成，请稍后重试。"}</p> : null}
      {explanation ? <div className="gapResult" aria-live="polite"><h3>{explanation.requirement.text}</h3><span className="stateBadge">{statusLabels[explanation.status]}</span><p>{explanation.explanation}</p><EvidenceList title="有来源的简历证据" items={explanation.evidence} />{explanation.candidate_evidence.length ? <EvidenceList title="待你核实的候选段落" items={explanation.candidate_evidence} /> : null}{explanation.clarification_question ? <p><strong>需要确认：</strong>{explanation.clarification_question}</p> : null}<p><strong>下一步：</strong>{explanation.next_action}</p><small>{explanation.mode === "langchain" ? "LangChain 辅助整理；事实仍按原文校验" : "基于已保存证据生成的基础解释"}</small></div> : null}
    </>}
  </section>;
}

function EvidenceList({ title, items }: { title: string; items: GapEvidence[] }) {
  return <div className="gapEvidence"><h4>{title}</h4>{items.length ? <ul>{items.map((item) => <li key={item.source_id}><p>“{item.text}”</p><small>{item.section} · {item.entry}{item.bullet_index == null ? "" : ` · 第 ${item.bullet_index + 1} 条`}</small><a className="textLink" href={`#resume-source-${item.source_id}`}>查看原文</a></li>)}</ul> : <p>暂无。</p>}</div>;
}
