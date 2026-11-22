"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import type { ApplicationMutationResult } from "@/lib/client-api-types";

type Evidence = {
  jobId: number;
  jobTitle: string;
  company: string;
  resumeId: number;
  resumeName: string;
  resumeVersion: number;
  matchId: number;
  matchScore: number;
};

async function responseBody<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null) as T | { error?: string | { message?: string } } | null;
  if (!response.ok) {
    const error = body && typeof body === "object" && "error" in body ? body.error : null;
    throw new Error(typeof error === "string" ? error : error?.message || "请求未能完成，请稍后重试");
  }
  return body as T;
}

export function ApplicationCreateForm({ evidence }: { evidence: Evidence }) {
  const router = useRouter();
  const [notes, setNotes] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (!confirmed) return setError("请确认所选岗位、简历和匹配报告");
    if (notes.length > 5_000) return setError("备注不能超过 5,000 个字符");
    setSubmitting(true);
    try {
      const response = await fetch("/api/backend/applications", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": `web-application-create-${crypto.randomUUID()}`,
        },
        body: JSON.stringify({
          job_id: evidence.jobId,
          resume_id: evidence.resumeId,
          match_id: evidence.matchId,
          notes: notes.trim(),
        }),
      });
      const result = await responseBody<ApplicationMutationResult>(response);
      router.push(`/dashboard/applications/${result.application.id}`);
      router.refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "申请记录创建失败");
      setSubmitting(false);
    }
  }

  return <div className="applicationCreateLayout">
    <section className="detailPanel evidenceConfirmation">
      <div className="panelHeading"><div><p className="eyebrow">历史证据快照</p><h2>确认申请上下文</h2></div><span className="stateBadge success">匹配 #{evidence.matchId}</span></div>
      <dl>
        <div><dt>目标岗位</dt><dd>{evidence.jobTitle}</dd><span>{evidence.company} · 岗位 #{evidence.jobId}</span></div>
        <div><dt>使用简历</dt><dd>{evidence.resumeName} · V{evidence.resumeVersion}</dd><span>简历 #{evidence.resumeId}</span></div>
        <div><dt>匹配报告</dt><dd>{Math.round(evidence.matchScore)}%</dd><span>报告 #{evidence.matchId} · 分数不是录用概率</span></div>
      </dl>
    </section>
    <section className="detailPanel">
      <div className="panelHeading"><div><p className="eyebrow">受控写入</p><h2>创建申请记录</h2></div></div>
      <p className="panelHint">新记录初始状态为“已收藏”。只有实际投递后，再在详情页推进为“已申请”。</p>
      <form className="applicationForm" onSubmit={submit}>
        <div className="fieldGroup"><label htmlFor="application-notes">初始备注（可选）</label><textarea id="application-notes" maxLength={5_000} rows={6} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="记录渠道、联系人或下一步准备事项，不要填写密码等敏感信息。" /><p className="fieldHint">{notes.length.toLocaleString()} / 5,000 字符</p></div>
        <label className="confirmationCheck"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /><span>我已确认岗位、简历版本和匹配报告，创建后将保存为历史申请上下文。</span></label>
        {error ? <p className="formError" role="alert">{error}</p> : null}
        <button className="primaryButton" disabled={submitting || !confirmed} type="submit">{submitting ? "正在创建…" : "创建申请记录"}</button>
      </form>
    </section>
  </div>;
}
