import Link from "next/link";

export function Pagination({ page, hasPrevious, hasNext }: { page: number; hasPrevious: boolean; hasNext: boolean }) {
  if (!hasPrevious && !hasNext) return null;
  return (
    <nav className="pagination" aria-label="分页">
      {hasPrevious ? <Link href={`?page=${page - 1}`}>上一页</Link> : <span aria-disabled="true">上一页</span>}
      <strong>第 {page} 页</strong>
      {hasNext ? <Link href={`?page=${page + 1}`}>下一页</Link> : <span aria-disabled="true">下一页</span>}
    </nav>
  );
}
