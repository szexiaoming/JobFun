"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";

import type { Operation, StoredObject } from "@/lib/client-api-types";

type ImportKind = "resume" | "job";

const CONFIG = {
  resume: {
    noun: "简历",
    endpoint: "/api/backend/resumes",
    uploadEndpoint: "/api/backend/uploads/resume_source",
    accept: ".txt,.pdf,.zip",
    allowed: ".txt、.pdf、.zip",
    maxBytes: 50 * 1024 * 1024,
    textMax: 200_000,
    resultKey: "resume_id",
    resultPath: "/dashboard/resumes",
  },
  job: {
    noun: "岗位",
    endpoint: "/api/backend/jobs",
    uploadEndpoint: "/api/backend/uploads/job_source",
    accept: ".png,.jpg,.jpeg,.webp,.pdf",
    allowed: ".png、.jpg、.jpeg、.webp、.pdf",
    maxBytes: 20 * 1024 * 1024,
    textMax: 100_000,
    resultKey: "job_id",
    resultPath: "/dashboard/jobs",
  },
} as const;

function idempotencyKey(prefix: string) {
  return `web-${prefix}-${crypto.randomUUID()}`;
}

async function responseBody<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null) as
    | T
    | { error?: string | { message?: string } }
    | null;
  if (!response.ok) {
    const error = body && typeof body === "object" && "error" in body ? body.error : null;
    const message = typeof error === "string" ? error : error?.message;
    throw new Error(message || "请求未能完成，请稍后重试");
  }
  return body as T;
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function OperationStatusCard({ operation, kind }: { operation: Operation; kind: ImportKind }) {
  const config = CONFIG[kind];
  const labels = { queued: "等待处理", running: "正在解析", succeeded: "解析完成", failed: "解析失败" };
  const resultId = operation.result_refs[config.resultKey];
  return <section className={`operationCard ${operation.status}`} aria-live="polite" aria-label="解析进度">
    <div className="operationHeading">
      <div><p className="eyebrow">异步解析</p><h3>{labels[operation.status]}</h3></div>
      <strong>{Math.max(0, Math.min(100, operation.progress))}%</strong>
    </div>
    <div className="progressTrack" aria-label={`解析进度 ${operation.progress}%`}><span style={{ width: `${Math.max(0, Math.min(100, operation.progress))}%` }} /></div>
    {operation.error_message ? <p className={operation.status === "failed" ? "operationError" : "operationNotice"}>{operation.error_message}</p> : null}
    {operation.retry_count > 0 && operation.status !== "succeeded" ? <p className="retryNote">系统已自动重试 {operation.retry_count} 次，无需重复提交。</p> : null}
    {operation.status === "succeeded" && resultId ? <Link className="primaryButton compact" href={`${config.resultPath}/${resultId}`}>查看{config.noun}详情</Link> : null}
    {operation.status === "failed" ? <p className="fieldHint">你可以检查内容后重新提交；新提交会使用新的幂等键。</p> : null}
  </section>;
}

export function ImportWorkspace({ kind }: { kind: ImportKind }) {
  const config = CONFIG[kind];
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [operation, setOperation] = useState<Operation | null>(null);
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [stored, setStored] = useState<StoredObject | null>(null);
  const [uploadError, setUploadError] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!operation || ["succeeded", "failed"].includes(operation.status)) return;
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`/api/backend/operations/${operation.id}`, { cache: "no-store" });
        const next = await responseBody<Operation>(response);
        if (!cancelled) setOperation(next);
      } catch (error) {
        if (!cancelled) setSubmitError(error instanceof Error ? error.message : "无法刷新解析进度");
      }
    }, 1200);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [operation]);

  async function submitText(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitError("");
    const cleanText = text.trim();
    const cleanName = name.trim();
    if (!cleanText) return setSubmitError(`请粘贴${config.noun}内容`);
    if (cleanText.length > config.textMax) return setSubmitError(`内容不能超过 ${config.textMax.toLocaleString()} 个字符`);
    if (kind === "resume" && !cleanName) return setSubmitError("请填写简历名称");
    if (kind === "resume" && cleanName.length > 200) return setSubmitError("简历名称不能超过 200 个字符");
    if (kind === "job" && sourceUrl.length > 2000) return setSubmitError("来源链接不能超过 2,000 个字符");
    setSubmitting(true);
    setOperation(null);
    try {
      const payload = kind === "resume" ? { name: cleanName, text: cleanText } : { text: cleanText, source_url: sourceUrl.trim() };
      const response = await fetch(config.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey(kind) },
        body: JSON.stringify(payload),
      });
      setOperation(await responseBody<Operation>(response));
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "提交失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  async function uploadFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setUploadError("");
    setStored(null);
    if (!file) return setUploadError("请先选择文件");
    if (file.size === 0) return setUploadError("不能上传空文件");
    if (file.size > config.maxBytes) return setUploadError(`文件不能超过 ${formatBytes(config.maxBytes)}`);
    setUploading(true);
    try {
      const data = new FormData();
      data.append("file", file);
      const response = await fetch(config.uploadEndpoint, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey(`${kind}-upload`) },
        body: data,
      });
      setStored(await responseBody<StoredObject>(response));
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "上传失败，请稍后重试");
    } finally {
      setUploading(false);
    }
  }

  return <div className="importGrid">
    <section className="importPanel">
      <div className="panelHeading"><div><p className="eyebrow">立即解析</p><h2>粘贴{config.noun}文本</h2></div><span className="stateBadge success">进入解析队列</span></div>
      <p className="panelHint">文本提交后会创建可追踪的异步任务；系统会自动刷新进度并展示重试状态。</p>
      <form className="importForm" onSubmit={submitText}>
        {kind === "resume" ? <div className="fieldGroup"><label htmlFor="resume-name">简历名称</label><input id="resume-name" maxLength={200} value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：后端工程师主简历" /></div> : <div className="fieldGroup"><label htmlFor="source-url">来源链接（可选）</label><input id="source-url" maxLength={2000} type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://example.com/job" /></div>}
        <div className="fieldGroup"><label htmlFor={`${kind}-text`}>{config.noun}原文</label><textarea id={`${kind}-text`} maxLength={config.textMax} required rows={14} value={text} onChange={(event) => setText(event.target.value)} placeholder={kind === "resume" ? "粘贴完整简历文本，AI 只基于你提供的真实内容进行结构化。" : "粘贴完整岗位描述，包括职责、要求和公司信息。"} /><p className="fieldHint">{text.length.toLocaleString()} / {config.textMax.toLocaleString()} 字符</p></div>
        {submitError ? <p className="formError" role="alert">{submitError}</p> : null}
        <button className="primaryButton" disabled={submitting} type="submit">{submitting ? "正在提交…" : `提交并解析${config.noun}`}</button>
      </form>
      {operation ? <OperationStatusCard operation={operation} kind={kind} /> : null}
    </section>

    <section className="importPanel uploadPanel">
      <div className="panelHeading"><div><p className="eyebrow">安全暂存</p><h2>上传{config.noun}文件</h2></div><span className="stateBadge">暂存源文件</span></div>
      <p className="panelHint">支持 {config.allowed}，最大 {formatBytes(config.maxBytes)}。文件由当前账户隔离存储。</p>
      <form className="importForm" onSubmit={uploadFile}>
        <div className="fileField"><label htmlFor={`${kind}-file`}>选择文件</label><input ref={fileInput} id={`${kind}-file`} type="file" accept={config.accept} onChange={(event) => { setFile(event.target.files?.[0] || null); setStored(null); setUploadError(""); }} />{file ? <p><strong>{file.name}</strong><span>{formatBytes(file.size)}</span></p> : <p className="fieldHint">文件只会发送到同源 BFF，不会在浏览器脚本中保存 Token。</p>}</div>
        {uploadError ? <p className="formError" role="alert">{uploadError}</p> : null}
        <button className="primaryButton" disabled={uploading || !file} type="submit">{uploading ? "正在上传…" : "安全暂存文件"}</button>
      </form>
      {stored ? <section className="storedCard" aria-live="polite"><p className="eyebrow">暂存完成</p><h3>{stored.original_name}</h3><dl><div><dt>对象编号</dt><dd>#{stored.id}</dd></div><div><dt>文件大小</dt><dd>{formatBytes(stored.size_bytes)}</dd></div><div><dt>存储状态</dt><dd>{stored.status}</dd></div></dl></section> : null}
      <div className="scopeNotice"><strong>当前能力边界</strong><p>文件已安全暂存，但当前 API 尚未把上传对象接入解析队列。要立即生成结构化{config.noun}记录，请使用左侧的文本导入。</p></div>
    </section>
  </div>;
}
