import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ApplicationCreateForm } from "@/components/application-create-form";
import { DetailHeader } from "@/components/detail-header";
import { getJob, getResume } from "@/lib/jobfun-api";
import { detailOrNotFound, resourceId } from "@/lib/resource-pages";

export const metadata: Metadata = { title: "创建申请" };

function single(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export default async function NewApplicationPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const search = await searchParams;
  const jobId = resourceId(single(search.job_id) || "");
  const resumeId = resourceId(single(search.resume_id) || "");
  const matchId = resourceId(single(search.match_id) || "");
  const [job, resume] = await Promise.all([detailOrNotFound(getJob(jobId)), detailOrNotFound(getResume(resumeId))]);
  if (!job.latest_match || job.latest_match.id !== matchId) notFound();
  return <div className="dashboardContent detailPage">
    <DetailHeader backHref="/dashboard/matches/new" backLabel="返回匹配工作区" eyebrow="申请记录" title="保存这次求职行动" description="确认岗位、简历版本和匹配报告后，创建一条可持续推进的申请记录。" />
    <ApplicationCreateForm evidence={{ jobId, jobTitle: job.position, company: job.company, resumeId, resumeName: resume.name, resumeVersion: resume.base_version, matchId, matchScore: job.latest_match.total_score }} />
  </div>;
}
