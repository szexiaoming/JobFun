import Link from "next/link";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link className="brand" href="/dashboard" aria-label="JobFun 工作台">
      <span className="brandMark" aria-hidden="true">
        <svg viewBox="0 0 32 32" role="img">
          <path d="M8 7h10v11.5A6.5 6.5 0 0 1 11.5 25H9v-4h2.5a2.5 2.5 0 0 0 2.5-2.5V11H8V7Z" />
          <path d="M20 7h7v4h-3v4h3v4h-3v6h-4V7Z" />
        </svg>
      </span>
      {!compact && (
        <span className="brandText">
          <strong>JobFun</strong>
          <small>AI 求职工作台</small>
        </span>
      )}
    </Link>
  );
}
