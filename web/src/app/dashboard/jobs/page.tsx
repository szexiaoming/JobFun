import type { Metadata } from "next";
import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { BriefcaseIcon } from "@/components/icons";
import { PageHeader } from "@/components/page-header";
import { Pagination } from "@/components/pagination";
import { listJobs, safePage } from "@/lib/jobfun-api";
import { formatDate, score, sourceLabel } from "@/lib/presentation";

export const metadata: Metadata = { title: "岗位" };
export default async function JobsPage({ searchParams }: { searchParams: Promise<{ page?: string | string[] }> }) {
  const page = safePage((await searchParams).page);
  const result = await listJobs(page);
  return <div className="dashboardContent">
    <PageHeader eyebrow="岗位中心" title="集中查看目标岗位" description="比较岗位来源、匹配结果与申请进度，所有数据均来自当前账户。" aside={<div className="headerActions"><Link className="secondaryButton compact" href="/dashboard/jobs/new">导入岗位</Link><Link className="primaryButton compact" href="/dashboard/matches/new">执行匹配</Link></div>} />
    {result.items.length === 0 ? <EmptyState title={page > 1 ? "这一页没有岗位" : "还没有岗位"} description={page > 1 ? "请返回上一页继续查看。" : "录入目标岗位后，匹配和申请概况会出现在这里。"} icon={<BriefcaseIcon />} /> :
      <section className="cardGrid" aria-label="岗位列表">{result.items.map((job) => <Link className="resourceCard resourceLink jobCard" href={`/dashboard/jobs/${job.id}`} key={job.id}>
        <div className="resourceTop"><span className="companyMark" aria-hidden="true">{job.company.slice(0, 1).toUpperCase()}</span><span className="stateBadge">{sourceLabel(job.source_type)}</span></div>
        <div><h2>{job.position}</h2><p>{job.company}</p></div>
        <div className="jobMetrics"><span><strong>{job.latest_match ? score(job.latest_match.total_score) : "—"}</strong>最新匹配</span><span><strong>{job.match_count}</strong>匹配记录</span><span><strong>{job.application_count}</strong>申请</span></div>
        <footer><span>岗位 #{job.id}</span><time>{formatDate(job.created_at, "日期未知")}</time></footer>
      </Link>)}</section>}
    <Pagination {...result} />
  </div>;
}
