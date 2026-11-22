"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import type { ApplicationMutationResult } from "@/lib/client-api-types";
import { statusLabel } from "@/lib/presentation";

const STATUS_TRANSITIONS: Record<string, string[]> = {
  saved: ["applied", "withdrawn"],
  applied: ["oa", "interview", "rejected", "withdrawn"],
  oa: ["interview", "rejected", "withdrawn"],
  interview: ["offer", "rejected", "withdrawn"],
  offer: ["accepted", "rejected", "withdrawn"],
  accepted: [],
  rejected: [],
  withdrawn: [],
};

type CurrentApplication = {
  id: number;
  status: string;
  nextStep: string;
  nextStepDue: string;
  interviewAt: string;
};

async function responseBody<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null) as T | { error?: string | { message?: string } } | null;
  if (!response.ok) {
    const error = body && typeof body === "object" && "error" in body ? body.error : null;
    throw new Error(typeof error === "string" ? error : error?.message || "请求未能完成，请稍后重试");
  }
  return body as T;
}

function toInputDateTime(value: string) {
  if (!value) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return `${value}T09:00`;
  const normalized = value.replace(" ", "T");
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(normalized) ? normalized.slice(0, 16) : "";
}

function toApiDateTime(value: string) {
  return value ? value.replace("T", " ") : "";
}

export function ApplicationUpdateForm({ current }: { current: CurrentApplication }) {
  const router = useRouter();
  const [nextStatus, setNextStatus] = useState("");
  const [note, setNote] = useState("");
  const [nextStep, setNextStep] = useState(current.nextStep);
  const initialDue = toInputDateTime(current.nextStepDue);
  const initialInterview = toInputDateTime(current.interviewAt);
  const [nextStepDue, setNextStepDue] = useState(initialDue);
  const [interviewAt, setInterviewAt] = useState(initialInterview);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const transitions = STATUS_TRANSITIONS[current.status] || [];

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
    const changes: Record<string, string> = {};
    if (nextStatus) changes.status = nextStatus;
    if (note.trim()) changes.note = note.trim();
    if (nextStep.trim() !== current.nextStep) changes.next_step = nextStep.trim();
    if (nextStepDue !== initialDue) changes.next_step_due = toApiDateTime(nextStepDue);
    if (interviewAt !== initialInterview) changes.interview_at = toApiDateTime(interviewAt);
    if (!Object.keys(changes).length) return setError("请至少修改一个字段或追加一条备注");
    if (note.length > 5_000) return setError("单条备注不能超过 5,000 个字符");
    if (nextStep.length > 500) return setError("下一步不能超过 500 个字符");
    setPending(true);
    try {
      const response = await fetch(`/api/backend/applications/${current.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": `web-application-update-${crypto.randomUUID()}`,
        },
        body: JSON.stringify(changes),
      });
      const result = await responseBody<ApplicationMutationResult>(response);
      setNextStatus("");
      setNote("");
      setNextStep(result.application.next_step || "");
      setNextStepDue(toInputDateTime(result.application.next_step_due));
      setInterviewAt(toInputDateTime(result.application.interview_at));
      setSuccess(`更新已保存 · 操作 #${result.operation.id}`);
      router.refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "申请记录更新失败");
    } finally {
      setPending(false);
    }
  }

  return <section className="detailPanel applicationEditPanel" aria-labelledby="application-edit-title">
    <div className="panelHeading"><div><p className="eyebrow">受控推进</p><h2 id="application-edit-title">更新申请记录</h2></div><span className="stateBadge">当前：{statusLabel(current.status)}</span></div>
    <form className="applicationForm" onSubmit={submit}>
      <div className="applicationEditGrid">
        <div className="fieldGroup"><label htmlFor="application-status">下一状态</label><span className="selectField"><select id="application-status" value={nextStatus} onChange={(event) => setNextStatus(event.target.value)} disabled={!transitions.length}><option value="">{transitions.length ? "保持当前状态" : "当前状态不可继续推进"}</option>{transitions.map((status) => <option key={status} value={status}>{statusLabel(status)}</option>)}</select></span><p className="fieldHint">状态只能按后端允许的路径逐步推进，不能跨级修改。</p></div>
        <div className="fieldGroup"><label htmlFor="application-next-step">下一步</label><input id="application-next-step" maxLength={500} value={nextStep} onChange={(event) => setNextStep(event.target.value)} placeholder="例如：准备系统设计案例" /></div>
        <div className="fieldGroup"><label htmlFor="application-due">行动截止时间</label><input id="application-due" type="datetime-local" value={nextStepDue} onChange={(event) => setNextStepDue(event.target.value)} /></div>
        <div className="fieldGroup"><label htmlFor="application-interview">面试时间</label><input id="application-interview" type="datetime-local" value={interviewAt} onChange={(event) => setInterviewAt(event.target.value)} /></div>
      </div>
      <div className="fieldGroup"><label htmlFor="application-note">追加备注</label><textarea id="application-note" maxLength={5_000} rows={4} value={note} onChange={(event) => setNote(event.target.value)} placeholder="新备注会追加到历史记录，不会覆盖已有内容。" /><p className="fieldHint">{note.length.toLocaleString()} / 5,000 字符</p></div>
      {error ? <p className="formError" role="alert">{error}</p> : null}
      {success ? <p className="formSuccess" role="status">{success}</p> : null}
      <button className="primaryButton compact" disabled={pending} type="submit">{pending ? "正在保存…" : "保存更新"}</button>
    </form>
  </section>;
}
