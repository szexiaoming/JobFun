import type { Metadata } from "next";

import { EmptyState } from "@/components/empty-state";
import { AudioIcon } from "@/components/icons";
import { PageHeader } from "@/components/page-header";
import { RetainedAudioManager } from "@/components/retained-audio-manager";
import { listRetainedAudio } from "@/lib/jobfun-api";

export const metadata: Metadata = { title: "保留音频" };

export default async function RetainedAudioPage() {
  const result = await listRetainedAudio();
  const maintenanceLabel = result.maintenance.status === "healthy"
    ? "自动清理正常"
    : result.maintenance.status === "warning"
      ? "清理出现单次失败"
      : "清理需要维护";
  return (
    <div className="dashboardContent">
      <PageHeader
        eyebrow="隐私与存储"
        title="管理保留的面试音频"
        description={`只有你主动选择保留的原音频会出现在这里；它们最多保存 ${result.retention_days} 天，也可以随时批量删除。`}
        aside={<span className={`connectionBadge ${result.maintenance.status}`}><span /> {maintenanceLabel}</span>}
      />
      <section className="retentionHealthGrid" aria-label="自动清理运行状态">
        <article><small>最近运行</small><strong>{runStatus(result.maintenance.task_status)}</strong><span>{ageLabel(result.maintenance.last_completed_age_seconds)}</span></article>
        <article><small>上次扫描</small><strong>{result.maintenance.last_checked}</strong><span>删除 {result.maintenance.last_deleted} · 失败 {result.maintenance.last_failed}</span></article>
        <article><small>累计运行</small><strong>{result.maintenance.run_total}</strong><span>累计删除 {result.maintenance.deleted_total}</span></article>
        <article><small>连续失败</small><strong>{result.maintenance.consecutive_failures}</strong><span>{result.maintenance.status === "degraded" ? "已达到告警条件" : "未达到告警条件"}</span></article>
      </section>
      <section className="retentionInsightGrid" aria-label="自动清理趋势与保留策略审计">
        <article className="retentionInsightCard">
          <div className="retentionInsightHeader">
            <div><small>运行趋势</small><h2>最近 {result.maintenance.trend.window_runs} 次清理</h2></div>
            <strong>{formatPercent(result.maintenance.trend.success_rate_percent)}</strong>
          </div>
          <p>共扫描 {result.maintenance.trend.checked_count} 条，删除 {result.maintenance.trend.deleted_count} 条，失败 {result.maintenance.trend.failed_count} 条。</p>
          {result.maintenance.recent_runs.length ? (
            <ol className="maintenanceRunList">
              {result.maintenance.recent_runs.slice(0, 5).map((run, index) => (
                <li key={`${run.completed_at}-${index}`}>
                  <span className={`runStateDot ${run.status}`} aria-hidden="true" />
                  <time dateTime={run.completed_at}>{formatTimestamp(run.completed_at)}</time>
                  <span>扫描 {run.checked_count} · 删除 {run.deleted_count} · 失败 {run.failed_count}</span>
                </li>
              ))}
            </ol>
          ) : <p className="retentionMuted">完成首次计划清理后，这里会显示最近运行趋势。</p>}
        </article>
        <article className="retentionInsightCard">
          <div className="retentionInsightHeader">
            <div><small>策略审计</small><h2>当前最多保留 {result.retention_policy.configured_days} 天</h2></div>
            <strong>{result.retention_policy.changes.length}</strong>
          </div>
          <p>{result.retention_policy.last_observed_at ? `最近核对：${formatTimestamp(result.retention_policy.last_observed_at)}` : "等待清理任务首次核对当前配置。"}</p>
          {result.retention_policy.changes.length ? (
            <ol className="policyChangeList">
              {result.retention_policy.changes.slice(0, 5).map((change, index) => (
                <li key={`${change.changed_at}-${index}`}>
                  <strong>{change.previous_days} 天 → {change.new_days} 天</strong>
                  <time dateTime={change.changed_at}>{formatTimestamp(change.changed_at)}</time>
                </li>
              ))}
            </ol>
          ) : <p className="retentionMuted">尚未发现保留期限变更；首次运行只建立基线，不记作变更。</p>}
        </article>
      </section>
      {result.items.length ? (
        <RetainedAudioManager items={result.items} />
      ) : (
        <EmptyState
          title="没有保留的原音频"
          description="默认情况下，语音转写完成后原音频会立即删除。"
          icon={<AudioIcon />}
        />
      )}
    </div>
  );
}

function runStatus(value: string) {
  return ({ succeeded: "成功", failed: "失败", running: "运行中" } as Record<string, string>)[value] || "等待首次运行";
}

function ageLabel(seconds: number | null) {
  if (seconds === null) return "尚无完成记录";
  if (seconds < 60) return "刚刚完成";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  return `${Math.floor(seconds / 3600)} 小时前`;
}

function formatPercent(value: number) {
  return `${Number.isFinite(value) ? value.toFixed(value % 1 ? 1 : 0) : "0"}%`;
}

function formatTimestamp(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "时间未知"
    : new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

