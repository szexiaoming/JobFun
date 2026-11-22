export const STATUS_LABELS: Record<string, string> = {
  saved: "已收藏",
  applied: "已申请",
  oa: "笔试中",
  screening: "筛选中",
  interview: "面试中",
  offer: "已录用",
  accepted: "已接受",
  rejected: "未通过",
  withdrawn: "已撤回",
};

export function statusLabel(status: string): string {
  return (STATUS_LABELS[status] ?? status) || "未知";
}

export function formatDate(value: string, fallback = "未设置"): string {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(date);
}

export function formatDateTime(value: string, fallback = "未安排"): string {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function sourceLabel(source: string): string {
  const labels: Record<string, string> = {
    text: "文本录入",
    url: "链接导入",
    file: "文件导入",
  };
  return labels[source] ?? source;
}

export function score(value: number): string {
  return `${Math.round(value)}%`;
}
