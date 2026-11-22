"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { RetainedAudio } from "@/lib/jobfun-api";

export function RetainedAudioManager({ items }: { items: RetainedAudio[] }) {
  const router = useRouter();
  const [selected, setSelected] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  function toggle(id: number) {
    setSelected((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
    setMessage("");
  }

  async function removeSelected() {
    if (!selected.length || busy) return;
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch("/api/backend/retained-audio", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ object_ids: selected }),
      });
      const body = await response.json() as { deleted?: number; error?: { message?: string } };
      if (!response.ok) throw new Error(body.error?.message || "暂时无法删除音频");
      setSelected([]);
      setMessage(`已删除 ${body.deleted || 0} 条原音频。`);
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "暂时无法删除音频");
    } finally {
      setBusy(false);
    }
  }

  const allSelected = items.length > 0 && selected.length === items.length;
  return (
    <section className="retainedAudioPanel" aria-labelledby="retained-audio-title">
      <div className="retainedAudioToolbar">
        <label>
          <input
            type="checkbox"
            checked={allSelected}
            onChange={() => setSelected(allSelected ? [] : items.map((item) => item.id))}
          />
          <span>选择全部 {items.length} 条</span>
        </label>
        <button className="primaryButton compact" type="button" disabled={!selected.length || busy} onClick={removeSelected}>
          {busy ? "正在删除…" : `删除所选${selected.length ? `（${selected.length}）` : ""}`}
        </button>
      </div>
      {message ? <p className="audioActionMessage" role="status">{message}</p> : null}
      <div className="retainedAudioList">
        {items.map((item) => (
          <label className={`retainedAudioCard${selected.includes(item.id) ? " selected" : ""}`} key={item.id}>
            <input type="checkbox" checked={selected.includes(item.id)} onChange={() => toggle(item.id)} />
            <span className="audioWave" aria-hidden="true">∿</span>
            <span className="audioDetails">
              <strong>{item.original_name}</strong>
              <span>{formatBytes(item.size_bytes)} · {item.content_type}</span>
            </span>
            <span className="audioExpiry"><small>自动删除</small><time dateTime={item.expires_at}>{formatDate(item.expires_at)}</time></span>
          </label>
        ))}
      </div>
    </section>
  );
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "日期未知" : new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "short", day: "numeric" }).format(date);
}

