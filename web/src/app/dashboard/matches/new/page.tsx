import type { Metadata } from "next";

import { DetailHeader } from "@/components/detail-header";
import { MatchWorkspace } from "@/components/match-workspace";
import { listMatchOptions } from "@/lib/jobfun-api";

export const metadata: Metadata = { title: "执行匹配" };

export default async function NewMatchPage() {
  const options = await listMatchOptions();
  return <div className="dashboardContent detailPage">
    <DetailHeader backHref="/dashboard/jobs" backLabel="返回岗位中心" eyebrow="证据匹配" title="比较简历与目标岗位" description="明确选择一个简历版本和一个岗位，跟踪异步分析并查看可追溯的匹配证据。" />
    <MatchWorkspace
      resumes={options.resumes.map((resume) => ({ id: resume.id, name: resume.name, base_version: resume.base_version, is_active: resume.is_active }))}
      jobs={options.jobs.map((job) => ({ id: job.id, company: job.company, position: job.position, match_count: job.match_count, latest_score: job.latest_match?.total_score ?? null }))}
    />
  </div>;
}
