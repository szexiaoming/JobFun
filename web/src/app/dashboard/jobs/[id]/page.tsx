import type { Metadata } from "next";

import { DetailHeader } from "@/components/detail-header";
import { BriefcaseIcon } from "@/components/icons";
import { MatchReport } from "@/components/match-report";
import { JobRequirements } from "@/components/structured-details";
import { getJob } from "@/lib/jobfun-api";
import { formatDate, sourceLabel } from "@/lib/presentation";
import { detailOrNotFound, resourceId } from "@/lib/resource-pages";

export const metadata: Metadata = { title: "岗位详情" };

export default async function JobDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const id = resourceId((await params).id);
  const job = await detailOrNotFound(getJob(id));
  return <div className="dashboardContent detailPage">
    <DetailHeader backHref="/dashboard/jobs" backLabel="返回岗位列表" eyebrow={`${job.company} · 岗位 #${job.id}`} title={job.position} description="从岗位要求到匹配差距，集中查看当前保存的只读证据。" badge={<span className="stateBadge">{sourceLabel(job.source_type)}</span>} />
    <section className="detailPanel jobSummaryPanel">
      <span className="largeResourceIcon company"><BriefcaseIcon /></span>
      <dl className="inlineFacts"><div><dt>公司</dt><dd>{job.company}</dd></div><div><dt>录入时间</dt><dd>{formatDate(job.created_at, "日期未知")}</dd></div><div><dt>匹配记录</dt><dd>{job.match_count}</dd></div><div><dt>关联申请</dt><dd>{job.application_count}</dd></div></dl>
    </section>
    <div className="detailTwoColumns">
      <section className="detailPanel" aria-labelledby="requirements-title"><div className="panelHeading"><div><p className="eyebrow">结构化解析</p><h2 id="requirements-title">岗位要求</h2></div></div><JobRequirements data={job.structured_json} /></section>
      <MatchReport match={job.latest_match} />
    </div>
    <section className="detailPanel rawTextPanel" aria-labelledby="raw-job-title"><div className="panelHeading"><div><p className="eyebrow">原始证据</p><h2 id="raw-job-title">岗位原文</h2></div></div>{job.raw_text ? <pre>{job.raw_text}</pre> : <p className="panelHint">没有保存可读取的岗位原文。</p>}</section>
  </div>;
}
