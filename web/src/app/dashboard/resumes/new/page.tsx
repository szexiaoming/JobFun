import type { Metadata } from "next";
import { DetailHeader } from "@/components/detail-header";
import { ImportWorkspace } from "@/components/import-workspace";

export const metadata: Metadata = { title: "导入简历" };

export default function NewResumePage() {
  return <div className="dashboardContent detailPage">
    <DetailHeader backHref="/dashboard/resumes" backLabel="返回简历中心" eyebrow="简历导入" title="建立可追踪的简历版本" description="粘贴真实经历并查看异步解析进度，或先安全暂存原始文件。" />
    <ImportWorkspace kind="resume" />
  </div>;
}
