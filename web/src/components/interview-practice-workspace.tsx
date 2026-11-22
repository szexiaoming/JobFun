"use client";

import { FormEvent, useEffect, useState } from "react";

import type { InterviewAttemptDetail, Operation } from "@/lib/client-api-types";
import type { InterviewInsights, InterviewQuestion } from "@/lib/jobfun-api";
import { InterviewVoicePractice } from "@/components/interview-voice-practice";

const CATEGORY_LABELS: Record<string, string> = {
  technical: "技术能力",
  project_deep_dive: "项目深挖",
  behavioral: "行为面试",
  english: "英文表达",
  system_design: "系统设计",
  general: "综合问题",
};

const DIFFICULTY_LABELS: Record<string, string> = { easy: "基础", medium: "进阶", hard: "挑战" };
const SCORE_LABELS: Record<string, string> = { completeness: "完整性", truthfulness: "真实性", technical: "技术正确性", structure: "表达结构" };

async function responseBody<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null) as T | { error?: string | { message?: string } } | null;
  if (!response.ok) {
    const error = body && typeof body === "object" && "error" in body ? body.error : null;
    throw new Error(typeof error === "string" ? error : error?.message || "请求未能完成，请稍后重试");
  }
  return body as T;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())) : [];
}

function feedbackText(value: unknown) {
  return typeof value === "string" ? value : "";
}

export function InterviewPracticeWorkspace({ applicationId, questions, insights }: { applicationId: number; questions: InterviewQuestion[]; insights: InterviewInsights }) {
  const [questionId, setQuestionId] = useState(questions[0]?.id ? String(questions[0].id) : "");
  const [answer, setAnswer] = useState("");
  const [mode, setMode] = useState<"text" | "voice">("text");
  const [operation, setOperation] = useState<Operation | null>(null);
  const [attempt, setAttempt] = useState<InterviewAttemptDetail | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const selected = questions.find((question) => String(question.id) === questionId);

  useEffect(() => {
    if (!operation || operation.status === "succeeded" || operation.status === "failed") return;
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`/api/backend/operations/${operation.id}`, { cache: "no-store" });
        const next = await responseBody<Operation>(response);
        if (cancelled) return;
        setOperation(next);
        const attemptId = next.result_refs.attempt_id;
        if (next.status === "succeeded" && attemptId) {
          const detailResponse = await fetch(`/api/backend/interview-attempts/${attemptId}`, { cache: "no-store" });
          setAttempt(await responseBody<InterviewAttemptDetail>(detailResponse));
        }
      } catch (requestError) {
        if (!cancelled) setError(requestError instanceof Error ? requestError.message : "无法刷新评估进度");
      }
    }, 1200);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [operation]);

  async function queueEvaluation(cleanAnswer: string, voice?: { transcriptionOperationId: number; retainAudio: boolean }) {
    setError("");
    setAttempt(null);
    const selectedQuestion = Number(questionId);
    if (!questions.some((question) => question.id === selectedQuestion)) return setError("请选择有效的面试题");
    if (!cleanAnswer) return setError("请先填写回答");
    if (cleanAnswer.length > 12_000) return setError("回答不能超过 12,000 个字符");
    setSubmitting(true);
    setOperation(null);
    try {
      const response = await fetch("/api/backend/interview-attempts", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": `web-interview-answer-${crypto.randomUUID()}`,
        },
        body: JSON.stringify({ application_id: applicationId, question_id: selectedQuestion, answer_text: cleanAnswer, transcription_operation_id: voice?.transcriptionOperationId, retain_audio: voice?.retainAudio || false }),
      });
      setOperation(await responseBody<Operation>(response));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "回答提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await queueEvaluation(answer.trim());
  }

  if (!questions.length) {
    return <section className="detailPanel interviewEmpty"><p className="eyebrow">面试题库</p><h2>还没有可练习的题目</h2><p>当前申请的匹配报告尚未生成面试题。题目生成能力仍保留在现有工作流中，本轮不会由前端伪造题目。</p></section>;
  }

  const busy = operation != null && !["succeeded", "failed"].includes(operation.status);
  return <>
    <section className="interviewOverview" aria-label="练习概况">
      <div><strong>{questions.length}</strong><span>可练习题目</span></div><div><strong>{insights.attempt_count}</strong><span>历史作答</span></div><div><strong>{insights.practiced_question_count}</strong><span>已练题目</span></div><div><strong>{insights.attempt_count ? `${insights.overall_average.toFixed(1)}/5` : "—"}</strong><span>历史均分</span></div>
    </section>
    <div className="interviewLayout">
      <aside className="detailPanel questionPicker" aria-label="面试题列表">
        <div className="panelHeading"><div><p className="eyebrow">题目选择</p><h2>本次练习</h2></div></div>
        <div className="questionList">{questions.map((question) => <button className={String(question.id) === questionId ? "questionChoice selected" : "questionChoice"} key={question.id} type="button" onClick={() => { setQuestionId(String(question.id)); setAnswer(""); setMode("text"); setOperation(null); setAttempt(null); setError(""); }}><span>{CATEGORY_LABELS[question.category] || question.category}<small>{DIFFICULTY_LABELS[question.difficulty] || question.difficulty}</small></span><strong>{question.question}</strong><em>{question.attempt_count ? `已练 ${question.attempt_count} 次${question.latest_score == null ? "" : ` · ${question.latest_score.toFixed(1)}/5`}` : "尚未练习"}</em></button>)}</div>
      </aside>
      <main className="detailPanel answerWorkspace">
        <div className="panelHeading"><div><p className="eyebrow">{mode === "text" ? "文字回答" : "语音回答"}</p><h2>{selected?.question}</h2></div><span className="stateBadge">{CATEGORY_LABELS[selected?.category || ""] || selected?.category}</span></div>
        <div className="answerModeTabs" role="tablist" aria-label="回答方式"><button role="tab" aria-selected={mode === "text"} className={mode === "text" ? "selected" : ""} type="button" onClick={() => { setMode("text"); setOperation(null); setAttempt(null); setError(""); }}>文字回答</button><button role="tab" aria-selected={mode === "voice"} className={mode === "voice" ? "selected" : ""} type="button" onClick={() => { setMode("voice"); setOperation(null); setAttempt(null); setError(""); }}>语音回答</button></div>
        <p className="panelHint">请只使用真实经历作答。评估会检查完整性、真实性、技术正确性和表达结构。</p>
        {mode === "text" ? <form className="interviewForm" onSubmit={submit}>
          <div className="fieldGroup"><label htmlFor="interview-answer">你的回答</label><textarea id="interview-answer" maxLength={12_000} rows={12} value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder="建议按背景、任务、行动、结果和复盘组织答案，并明确区分个人贡献与团队成果。" /><p className="fieldHint">{answer.length.toLocaleString()} / 12,000 字符</p></div>
          {error ? <p className="formError" role="alert">{error}</p> : null}
          <button className="primaryButton" disabled={submitting || busy} type="submit">{submitting ? "正在提交…" : busy ? "正在评估…" : "提交文字回答"}</button>
        </form> : <InterviewVoicePractice key={questionId} applicationId={applicationId} questionId={Number(questionId)} disabled={submitting || busy} onEvaluate={({ answerText, transcriptionOperationId, retainAudio }) => queueEvaluation(answerText, { transcriptionOperationId, retainAudio })} />}
        {operation ? <section className={`interviewOperation ${operation.status}`} aria-live="polite"><div><strong>{operation.status === "queued" ? "等待评估" : operation.status === "running" ? "正在评估" : operation.status === "succeeded" ? "评估完成" : "评估失败"}</strong><span>{operation.progress}%</span></div><div className="progressTrack" aria-label={`评估进度 ${operation.progress}%`}><span style={{ width: `${Math.max(0, Math.min(100, operation.progress))}%` }} /></div>{operation.error_message ? <p>{operation.error_message}</p> : null}{operation.retry_count > 0 && operation.status !== "succeeded" ? <p>系统已自动重试 {operation.retry_count} 次，无需重复提交。</p> : null}</section> : null}
      </main>
    </div>
    {attempt ? <InterviewReview attempt={attempt} /> : null}
  </>;
}

function InterviewReview({ attempt }: { attempt: InterviewAttemptDetail }) {
  const summary = feedbackText(attempt.feedback.summary);
  const nextPractice = feedbackText(attempt.feedback.next_practice);
  const strengths = stringList(attempt.feedback.strengths);
  const improvements = stringList(attempt.feedback.improvements);
  const unsupported = Array.isArray(attempt.feedback.unsupported_claims) ? attempt.feedback.unsupported_claims : [];
  return <section className="detailPanel interviewReview" aria-labelledby="interview-review-title">
    <div className="reviewLead"><div><p className="eyebrow">评估 #{attempt.id} · {attempt.answer_mode === "voice" ? "语音转写" : "文字回答"}</p><h2 id="interview-review-title">本次回答复盘</h2><p>{summary || "评估已完成，请结合四维分数继续复盘。"}</p>{attempt.answer_mode === "voice" ? <span className="stateBadge">{attempt.audio_retained ? "原音频已保留" : "原音频已删除"}</span> : null}</div><strong>{attempt.overall_score.toFixed(1)}<small>/5</small></strong></div>
    <div className="interviewScores">{Object.entries(SCORE_LABELS).map(([key, label]) => { const value = Number(attempt.scores[key]) || 0; return <div key={key}><span>{label}</span><div><i style={{ width: `${Math.max(0, Math.min(100, value / 5 * 100))}%` }} /></div><strong>{value.toFixed(1)}</strong></div>; })}</div>
    <div className="reviewColumns"><ReviewList title="做得好的地方" values={strengths} empty="本次没有返回明确优势。" /><ReviewList title="优先改进" values={improvements} empty="本次没有返回明确改进项。" /></div>
    {unsupported.length ? <div className="truthfulnessWarning"><strong>需要核实的表达</strong><ul>{unsupported.map((item, index) => { const record = item && typeof item === "object" ? item as Record<string, unknown> : {}; return <li key={index}>{feedbackText(record.claim) || "未命名表述"}{feedbackText(record.reason) ? `：${feedbackText(record.reason)}` : ""}</li>; })}</ul></div> : null}
    {nextPractice ? <div className="nextPractice"><strong>下一次练习</strong><p>{nextPractice}</p></div> : null}
    <details><summary>查看本次原回答</summary><p>{attempt.answer_text}</p></details>
  </section>;
}

function ReviewList({ title, values, empty }: { title: string; values: string[]; empty: string }) {
  return <div><h3>{title}</h3>{values.length ? <ul>{values.map((value, index) => <li key={`${value}-${index}`}>{value}</li>)}</ul> : <p>{empty}</p>}</div>;
}
