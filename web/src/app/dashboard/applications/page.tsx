import type { Metadata } from "next";
import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { ShieldIcon } from "@/components/icons";
import { PageHeader } from "@/components/page-header";
import { Pagination } from "@/components/pagination";
import { listApplications, safePage } from "@/lib/jobfun-api";
import { formatDate, formatDateTime, score, statusLabel } from "@/lib/presentation";

export const metadata: Metadata = { title: "申请" };
export default async function ApplicationsPage({ searchParams }: { searchParams: Promise<{ page?: string | string[] }> }) {
  const page = safePage((await searchParams).page);
  const result = await listApplications(page);
  return <div className="dashboardContent">
    <PageHeader eyebrow="申请跟踪" title="让每次推进都有依据" description="查看申请状态、简历版本、匹配分数和下一步安排；每次更新都会保留可追踪记录。" aside={<Link className="primaryButton compact" href="/dashboard/matches/new">从匹配创建</Link>} />
    {result.items.length === 0 ? <EmptyState title={page > 1 ? "这一页没有申请" : "还没有申请记录"} description={page > 1 ? "请返回上一页继续查看。" : "建立第一条申请后，它的推进状态会显示在这里。"} icon={<ShieldIcon />} /> :
      <section className="applicationList" aria-label="申请列表">{result.items.map((application) => <Link className="applicationCard applicationLink" href={`/dashboard/applications/${application.id}`} key={application.id}>
        <div className="applicationCompany"><span className="companyMark" aria-hidden="true">{application.job.company.slice(0, 1).toUpperCase()}</span><div><h2>{application.job.position}</h2><p>{application.job.company}</p></div></div>
        <div className="applicationMeta"><span><small>当前状态</small><strong className="statusText">{statusLabel(application.status)}</strong></span><span><small>使用简历</small><strong>{application.resume.name} · V{application.resume.base_version}</strong></span><span><small>匹配分数</small><strong>{application.match ? score(application.match.total_score) : "未匹配"}</strong></span><span><small>申请日期</small><strong>{formatDate(application.applied_date)}</strong></span></div>
        <div className="nextStep"><span>{application.next_step || "暂未设置下一步"}</span><time>{application.interview_at ? `面试 ${formatDateTime(application.interview_at)}` : application.next_step_due ? `截止 ${formatDate(application.next_step_due)}` : "暂无日期"}</time></div>
      </Link>)}</section>}
    <Pagination {...result} />
  </div>;
}
