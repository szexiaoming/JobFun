import type { Metadata } from "next";

import { DetailHeader } from "@/components/detail-header";
import { InterviewPracticeWorkspace } from "@/components/interview-practice-workspace";
import { getApplication, getInterviewInsights, listInterviewQuestions } from "@/lib/jobfun-api";
import { detailOrNotFound, resourceId } from "@/lib/resource-pages";

export const metadata: Metadata = { title: "面试练习" };

export default async function InterviewPracticePage({ params }: { params: Promise<{ id: string }> }) {
  const id = resourceId((await params).id);
  const [application, questions, insights] = await Promise.all([
    detailOrNotFound(getApplication(id)),
    detailOrNotFound(listInterviewQuestions(id)),
    detailOrNotFound(getInterviewInsights(id)),
  ]);
  return <div className="dashboardContent detailPage">
    <DetailHeader backHref={`/dashboard/applications/${id}`} backLabel="返回申请详情" eyebrow={`${application.job.company} · 申请 #${id}`} title="文字面试练习" description="围绕当前申请的匹配证据作答，跟踪异步评估，并用固定四维标准复盘。" />
    <InterviewPracticeWorkspace applicationId={id} questions={questions} insights={insights} />
  </div>;
}
