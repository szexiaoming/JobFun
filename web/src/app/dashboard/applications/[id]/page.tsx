import type { Metadata } from "next";
import Link from "next/link";

import { DetailHeader } from "@/components/detail-header";
import { ApplicationUpdateForm } from "@/components/application-update-form";
import { MatchReport } from "@/components/match-report";
import { JobRequirements, ResumeOutline } from "@/components/structured-details";
import { getApplication } from "@/lib/jobfun-api";
import { formatDate, formatDateTime, statusLabel } from "@/lib/presentation";
import { detailOrNotFound, resourceId } from "@/lib/resource-pages";

export const metadata: Metadata = { title: "申请详情" };

export default async function ApplicationDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const id = resourceId((await params).id);
  const application = await detailOrNotFound(getApplication(id));
  return <div className="dashboardContent detailPage">
    <DetailHeader backHref="/dashboard/applications" backLabel="返回申请列表" eyebrow={`${application.job.company} · 申请 #${application.id}`} title={application.job.position} description="查看申请当时绑定的岗位、简历和匹配证据，避免历史上下文漂移。" badge={<div className="headerActions"><span className="stateBadge success">{statusLabel(application.status)}</span>{application.match ? <Link className="primaryButton compact" href={`/dashboard/applications/${application.id}/interview`}>面试练习</Link> : null}</div>} />
    <section className="detailPanel applicationTimeline">
      <dl className="inlineFacts"><div><dt>申请日期</dt><dd>{formatDate(application.applied_date)}</dd></div><div><dt>下一步</dt><dd>{application.next_step || "未设置"}</dd></div><div><dt>行动截止</dt><dd>{formatDate(application.next_step_due)}</dd></div><div><dt>面试安排</dt><dd>{formatDateTime(application.interview_at)}</dd></div></dl>
    </section>
    <ApplicationUpdateForm current={{ id: application.id, status: application.status, nextStep: application.next_step, nextStepDue: application.next_step_due, interviewAt: application.interview_at }} />
    <MatchReport match={application.match} />
    <div className="detailTwoColumns snapshotColumns">
      <section className="detailPanel"><div className="panelHeading"><div><p className="eyebrow">历史岗位快照</p><h2>{application.job.position}</h2></div>{application.job.id > 0 && <Link className="textLink" href={`/dashboard/jobs/${application.job.id}`}>查看当前岗位详情</Link>}</div><JobRequirements data={application.job.structured_json} /></section>
      <section className="detailPanel"><div className="panelHeading"><div><p className="eyebrow">历史简历快照</p><h2>{application.resume.name} · V{application.resume.base_version}</h2></div>{application.resume.id > 0 && <Link className="textLink" href={`/dashboard/resumes/${application.resume.id}`}>查看当前简历详情</Link>}</div><ResumeOutline data={application.resume.structured_json} compact /></section>
    </div>
    <section className="detailPanel notePanel" aria-labelledby="notes-title"><div className="panelHeading"><div><p className="eyebrow">申请备注</p><h2 id="notes-title">记录</h2></div></div><p>{application.notes || "暂无备注。"}</p></section>
  </div>;
}
