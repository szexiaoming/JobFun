"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import type { MatchJobOption, MatchResumeOption, Operation } from "@/lib/client-api-types";

type ErrorBody = { error?: string | { message?: string } };

async function responseBody<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null) as T | ErrorBody | null;
  if (!response.ok) {
    const error = body && typeof body === "object" && "error" in body ? body.error : null;
    throw new Error(typeof error === "string" ? error : error?.message || "请求未能完成，请稍后重试");
  }
  return body as T;
}

const statusLabel = {
  queued: "等待匹配",
  running: "正在分析证据",
  succeeded: "匹配完成",
  failed: "匹配失败",
};

export function MatchWorkspace({ resumes, jobs }: { resumes: MatchResumeOption[]; jobs: MatchJobOption[] }) {
  const [resumeId, setResumeId] = useState(resumes[0]?.id ? String(resumes[0].id) : "");
  const [jobId, setJobId] = useState(jobs[0]?.id ? String(jobs[0].id) : "");
  const [operation, setOperation] = useState<Operation | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!operation || operation.status === "succeeded" || operation.status === "failed") return;
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`/api/backend/operations/${operation.id}`, { cache: "no-store" });
        const next = await responseBody<Operation>(response);
        if (!cancelled) setOperation(next);
      } catch (requestError) {
        if (!cancelled) setError(requestError instanceof Error ? requestError.message : "无法刷新匹配进度");
      }
    }, 1200);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [operation]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const selectedResume = Number(resumeId);
    const selectedJob = Number(jobId);
    if (!Number.isSafeInteger(selectedResume) || selectedResume <= 0 || !resumes.some((resume) => resume.id === selectedResume)) {
      return setError("请选择有效的简历版本");
    }
    if (!Number.isSafeInteger(selectedJob) || selectedJob <= 0 || !jobs.some((job) => job.id === selectedJob)) {
      return setError("请选择有效的目标岗位");
    }
    setSubmitting(true);
    setOperation(null);
    try {
      const response = await fetch("/api/backend/matches", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": `web-match-${crypto.randomUUID()}`,
        },
        body: JSON.stringify({ resume_id: selectedResume, job_id: selectedJob }),
      });
      setOperation(await responseBody<Operation>(response));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "匹配任务提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  const selectedResume = resumes.find((resume) => String(resume.id) === resumeId);
  const selectedJob = jobs.find((job) => String(job.id) === jobId);
  const progress = operation ? Math.max(0, Math.min(100, operation.progress)) : 0;
  const matchId = operation?.result_refs.match_id;

  if (!resumes.length || !jobs.length) {
    return <section className="detailPanel matchPrerequisite">
      <p className="eyebrow">准备数据</p>
      <h2>还不能执行匹配</h2>
      <p>匹配至少需要一份已有简历和一个已有岗位。请先补齐缺少的资源。</p>
      <div className="headerActions">
        {!resumes.length ? <Link className="primaryButton compact" href="/dashboard/resumes/new">导入简历</Link> : null}
        {!jobs.length ? <Link className="primaryButton compact" href="/dashboard/jobs/new">导入岗位</Link> : null}
      </div>
    </section>;
  }

  return <div className="matchExecutionLayout">
    <section className="detailPanel">
      <div className="panelHeading"><div><p className="eyebrow">证据选择</p><h2>选择匹配组合</h2></div><span className="stateBadge">不会创建申请</span></div>
      <p className="panelHint">AI 只比较所选简历中已有的证据与岗位要求。匹配分数不是录用概率，也不会修改你的简历。</p>
      <form className="matchForm" onSubmit={submit}>
        <div className="fieldGroup">
          <label htmlFor="match-resume">简历版本</label>
          <span className="selectField"><select id="match-resume" value={resumeId} onChange={(event) => { setResumeId(event.target.value); setOperation(null); setError(""); }}>
            {resumes.map((resume) => <option key={resume.id} value={resume.id}>{resume.name} · V{resume.base_version}{resume.is_active ? " · 使用中" : " · 已停用"}</option>)}
          </select></span>
        </div>
        <div className="fieldGroup">
          <label htmlFor="match-job">目标岗位</label>
          <span className="selectField"><select id="match-job" value={jobId} onChange={(event) => { setJobId(event.target.value); setOperation(null); setError(""); }}>
            {jobs.map((job) => <option key={job.id} value={job.id}>{job.position} · {job.company}</option>)}
          </select></span>
        </div>
        <div className="matchSelectionSummary" aria-live="polite">
          <div><span>简历</span><strong>{selectedResume?.name} · V{selectedResume?.base_version}</strong></div>
          <div><span>岗位</span><strong>{selectedJob?.position} · {selectedJob?.company}</strong></div>
          <div><span>历史匹配</span><strong>{selectedJob?.match_count || 0} 次{selectedJob?.latest_score == null ? "" : ` · 最新 ${Math.round(selectedJob.latest_score)} 分`}</strong></div>
        </div>
        {error ? <p className="formError" role="alert">{error}</p> : null}
        <button className="primaryButton" disabled={submitting || (operation != null && !["succeeded", "failed"].includes(operation.status))} type="submit">{submitting ? "正在提交…" : "开始证据匹配"}</button>
      </form>
    </section>

    <section className="detailPanel matchOperationPanel" aria-live="polite">
      <div className="panelHeading"><div><p className="eyebrow">异步任务</p><h2>{operation ? statusLabel[operation.status] : "等待开始"}</h2></div>{operation ? <strong className="operationPercent">{progress}%</strong> : null}</div>
      {!operation ? <div className="matchWaiting"><span aria-hidden="true">◎</span><p>提交后会在这里显示分析进度、自动重试状态和最终报告入口。</p></div> : <>
        <div className="progressTrack" aria-label={`匹配进度 ${progress}%`}><span style={{ width: `${progress}%` }} /></div>
        <dl className="operationFacts"><div><dt>任务编号</dt><dd>#{operation.id}</dd></div><div><dt>简历</dt><dd>#{resumeId}</dd></div><div><dt>岗位</dt><dd>#{jobId}</dd></div>{matchId ? <div><dt>匹配报告</dt><dd>#{matchId}</dd></div> : null}</dl>
        {operation.error_message ? <p className={operation.status === "failed" ? "operationError" : "operationNotice"}>{operation.error_message}</p> : null}
        {operation.retry_count > 0 && operation.status !== "succeeded" ? <p className="retryNote">系统已自动重试 {operation.retry_count} 次，无需重复提交。</p> : null}
        {operation.status === "succeeded" && matchId ? <div className="matchResult"><strong>匹配证据已生成</strong><p>报告已保存到所选岗位的最新匹配记录中。</p><div className="headerActions"><Link className="secondaryButton compact" href={`/dashboard/jobs/${jobId}#match-report-title`}>查看匹配报告</Link><Link className="primaryButton compact" href={`/dashboard/applications/new?job_id=${jobId}&resume_id=${resumeId}&match_id=${matchId}`}>记录申请</Link></div></div> : null}
        {operation.status === "failed" ? <p className="fieldHint">你可以保持当前组合重新提交；新任务会使用新的幂等键。</p> : null}
      </>}
    </section>
  </div>;
}
