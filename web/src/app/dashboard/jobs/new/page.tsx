import type { Metadata } from "next";
import { DetailHeader } from "@/components/detail-header";
import { ImportWorkspace } from "@/components/import-workspace";

export const metadata: Metadata = { title: "导入岗位" };

export default function NewJobPage() {
  return <div className="dashboardContent detailPage">
    <DetailHeader backHref="/dashboard/jobs" backLabel="返回岗位中心" eyebrow="岗位导入" title="把目标岗位放进工作台" description="粘贴岗位描述并跟踪结构化解析，或先安全暂存招聘页面截图与 PDF。" />
    <ImportWorkspace kind="job" />
  </div>;
}
