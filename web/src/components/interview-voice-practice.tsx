"use client";

import { ChangeEvent, useEffect, useRef, useState } from "react";

import type { InterviewTranscriptionDraft, Operation, StoredObject } from "@/lib/client-api-types";

const MAX_AUDIO_BYTES = 10 * 1024 * 1024;
const AUDIO_EXTENSIONS = ["flac", "mp3", "mp4", "mpeg", "mpga", "m4a", "ogg", "wav", "webm"];

type VoiceEvaluation = {
  answerText: string;
  transcriptionOperationId: number;
  retainAudio: boolean;
};

async function responseBody<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null) as T | { error?: string | { message?: string } } | null;
  if (!response.ok) {
    const error = body && typeof body === "object" && "error" in body ? body.error : null;
    throw new Error(typeof error === "string" ? error : error?.message || "请求未能完成，请稍后重试");
  }
  return body as T;
}

function idempotencyKey(prefix: string) {
  return `web-${prefix}-${crypto.randomUUID()}`;
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function validateAudio(file: File) {
  const extension = file.name.split(".").pop()?.toLowerCase() || "";
  if (!AUDIO_EXTENSIONS.includes(extension)) throw new Error(`仅支持 ${AUDIO_EXTENSIONS.join("、")} 音频`);
  if (!file.size) throw new Error("音频不能为空");
  if (file.size > MAX_AUDIO_BYTES) throw new Error("音频不能超过 10 MB");
}

export function InterviewVoicePractice({ applicationId, questionId, disabled, onEvaluate }: { applicationId: number; questionId: number; disabled: boolean; onEvaluate: (value: VoiceEvaluation) => void }) {
  const [consented, setConsented] = useState(false);
  const [retainOriginal, setRetainOriginal] = useState(false);
  const [keepAfterEvaluation, setKeepAfterEvaluation] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [stored, setStored] = useState<StoredObject | null>(null);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [draft, setDraft] = useState<InterviewTranscriptionDraft | null>(null);
  const [transcript, setTranscript] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  useEffect(() => {
    if (!operation || ["succeeded", "failed"].includes(operation.status)) return;
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const next = await responseBody<Operation>(await fetch(`/api/backend/operations/${operation.id}`, { cache: "no-store" }));
        if (cancelled) return;
        setOperation(next);
        if (next.status === "succeeded") {
          const nextDraft = await responseBody<InterviewTranscriptionDraft>(await fetch(`/api/backend/interview-transcriptions/${next.id}`, { cache: "no-store" }));
          setDraft(nextDraft);
          setTranscript(nextDraft.transcript);
          setKeepAfterEvaluation(nextDraft.audio_retained);
        }
      } catch (requestError) {
        if (!cancelled) setError(requestError instanceof Error ? requestError.message : "无法刷新转写进度");
      }
    }, 1200);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [operation]);

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] || null;
    setError("");
    setFile(null);
    if (!selected) return;
    try {
      validateAudio(selected);
      setFile(selected);
    } catch (selectionError) {
      setError(selectionError instanceof Error ? selectionError.message : "音频无效");
      event.target.value = "";
    }
  }

  async function startRecording() {
    setError("");
    if (!consented) return setError("请先确认音频处理方式");
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") return setError("当前浏览器不支持录音，请改用音频文件");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      streamRef.current = stream;
      recorderRef.current = recorder;
      chunksRef.current = [];
      recorder.ondataavailable = (event) => { if (event.data.size) chunksRef.current.push(event.data); };
      recorder.onstop = () => {
        const type = recorder.mimeType || "audio/webm";
        const extension = type.includes("wav") ? "wav" : "webm";
        const recorded = new File(chunksRef.current, `jobfun-answer-${Date.now()}.${extension}`, { type });
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        setRecording(false);
        try { validateAudio(recorded); setFile(recorded); } catch (recordError) { setError(recordError instanceof Error ? recordError.message : "录音无效"); }
      };
      recorder.start();
      setFile(null);
      setRecording(true);
    } catch {
      setError("无法使用麦克风。请检查浏览器权限，或改用音频文件。");
    }
  }

  function stopRecording() {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }

  async function transcribe() {
    setError("");
    if (!consented) return setError("请先确认音频处理方式");
    if (!file) return setError("请先录音或选择音频文件");
    try { validateAudio(file); } catch (validationError) { return setError(validationError instanceof Error ? validationError.message : "音频无效"); }
    setBusy(true);
    try {
      const data = new FormData();
      data.append("file", file);
      const uploaded = await responseBody<StoredObject>(await fetch("/api/backend/uploads/interview_audio", { method: "POST", headers: { "Idempotency-Key": idempotencyKey("voice-upload") }, body: data }));
      setStored(uploaded);
      const queued = await responseBody<Operation>(await fetch("/api/backend/interview-transcriptions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey("voice-transcription") },
        body: JSON.stringify({ application_id: applicationId, question_id: questionId, object_id: uploaded.id, retain_audio: retainOriginal }),
      }));
      setOperation(queued);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "音频转写提交失败");
    } finally {
      setBusy(false);
    }
  }

  async function deleteAudio() {
    if (!stored) return;
    setBusy(true);
    setError("");
    try {
      await responseBody<{ id: number; status: "deleted" }>(await fetch(`/api/backend/uploads/${stored.id}`, { method: "DELETE" }));
      setStored(null);
      setKeepAfterEvaluation(false);
      if (draft) setDraft({ ...draft, audio_retained: false });
      else resetAudio();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "音频删除失败");
    } finally {
      setBusy(false);
    }
  }

  function resetAudio() {
    setFile(null); setStored(null); setOperation(null); setDraft(null); setTranscript(""); setConfirmed(false); setKeepAfterEvaluation(false);
    if (inputRef.current) inputRef.current.value = "";
  }

  function confirmTranscript() {
    const clean = transcript.trim();
    if (!draft) return setError("请先完成音频转写");
    if (!confirmed) return setError("请确认已经检查转写内容");
    if (!clean || clean.length > 12_000) return setError("确认后的转写必须为 1–12,000 个字符");
    onEvaluate({ answerText: clean, transcriptionOperationId: draft.operation_id, retainAudio: draft.audio_retained && keepAfterEvaluation });
  }

  const transcribing = operation != null && !["succeeded", "failed"].includes(operation.status);
  return <div className="voicePractice">
    <div className="voiceConsent"><label><input type="checkbox" checked={consented} disabled={Boolean(stored)} onChange={(event) => setConsented(event.target.checked)} /><span><strong>我同意为本次练习处理音频</strong><small>只有点击“开始录音”时才请求麦克风权限；也可以只选择本地音频文件。</small></span></label></div>
    <div className="retentionChoice"><label><input type="checkbox" checked={retainOriginal} disabled={!consented || Boolean(stored)} onChange={(event) => setRetainOriginal(event.target.checked)} /><span><strong>转写后暂时保留原音频</strong><small>默认在转写完成后立即删除原音频，仅保留 24 小时可编辑转写草稿。主动保留的音频会按隐私策略自动到期，也可在“音频”页面提前批量删除。</small></span></label></div>
    <div className="voiceInputGrid">
      <div className="recordingCard"><span className={recording ? "recordingDot active" : "recordingDot"} aria-hidden="true" /><div><strong>{recording ? "正在录音" : "浏览器录音"}</strong><p>建议控制在 5 分钟内，WAV 会在服务端校验真实时长。</p></div>{recording ? <button className="secondaryButton compact" type="button" onClick={stopRecording}>停止录音</button> : <button className="secondaryButton compact" type="button" disabled={!consented || Boolean(stored)} onClick={startRecording}>开始录音</button>}</div>
      <div className="fileField voiceFile"><label htmlFor={`voice-file-${questionId}`}>或选择音频文件</label><input ref={inputRef} id={`voice-file-${questionId}`} type="file" accept=".flac,.mp3,.mp4,.mpeg,.mpga,.m4a,.ogg,.wav,.webm,audio/*" disabled={!consented || Boolean(stored) || recording} onChange={chooseFile} />{file ? <p><strong>{file.name}</strong><span>{formatBytes(file.size)}</span></p> : <p className="fieldHint">支持常见音频格式，最大 10 MB。</p>}</div>
    </div>
    {error ? <p className="formError" role="alert">{error}</p> : null}
    {!draft ? <button className="primaryButton" type="button" disabled={!file || busy || transcribing || disabled} onClick={transcribe}>{busy ? "正在上传…" : transcribing ? "正在转写…" : "上传并生成转写草稿"}</button> : null}
    {operation ? <section className={`interviewOperation ${operation.status}`} aria-live="polite"><div><strong>{operation.status === "queued" ? "等待转写" : operation.status === "running" ? "正在转写" : operation.status === "succeeded" ? "转写完成" : "转写失败"}</strong><span>{operation.progress}%</span></div><div className="progressTrack" aria-label={`转写进度 ${operation.progress}%`}><span style={{ width: `${Math.max(0, Math.min(100, operation.progress))}%` }} /></div>{operation.error_message ? <p>{operation.error_message}</p> : null}</section> : null}
    {draft ? <section className="transcriptDraft"><div className="panelHeading"><div><p className="eyebrow">可编辑草稿</p><h3>检查转写内容</h3></div><span className={draft.audio_retained ? "stateBadge" : "stateBadge success"}>{draft.audio_retained ? "原音频已保留" : "原音频已删除"}</span></div><p className="fieldHint">{draft.original_name} · {formatBytes(draft.size_bytes)} · 草稿 24 小时后失效</p><textarea rows={11} maxLength={12_000} value={transcript} onChange={(event) => { setTranscript(event.target.value); setConfirmed(false); }} /><label className="confirmationCheck"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /><span>我已检查并修改转写内容，确认它准确表达了我的回答。</span></label>{draft.audio_retained ? <label className="confirmationCheck"><input type="checkbox" checked={keepAfterEvaluation} onChange={(event) => setKeepAfterEvaluation(event.target.checked)} /><span>完成评价后继续保留原音频；取消勾选将在评价前删除。</span></label> : null}<div className="voiceActions"><button className="primaryButton" type="button" disabled={!confirmed || disabled} onClick={confirmTranscript}>确认转写并评价</button>{draft.audio_retained ? <button className="dangerTextButton" type="button" disabled={busy || disabled} onClick={deleteAudio}>删除保留的原音频</button> : null}</div></section> : stored && !draft && !transcribing ? <button className="dangerTextButton" type="button" disabled={busy} onClick={deleteAudio}>删除已上传音频</button> : null}
  </div>;
}
