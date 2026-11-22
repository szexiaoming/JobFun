import type { Metadata } from "next";

import { DetailHeader } from "@/components/detail-header";
import { FileIcon } from "@/components/icons";
import { ResumeOutline } from "@/components/structured-details";
import { getResume } from "@/lib/jobfun-api";
import { formatDate } from "@/lib/presentation";
import { detailOrNotFound, resourceId } from "@/lib/resource-pages";

export const metadata: Metadata = { title: "简历详情" };

export default async function ResumeDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const id = resourceId((await params).id);
  const resume = await detailOrNotFound(getResume(id));
  return <div className="dashboardContent detailPage">
    <DetailHeader backHref="/dashboard/resumes" backLabel="返回简历列表" eyebrow={`简历 #${resume.id}`} title={resume.name} description="查看该版本保存的真实经历结构；本页面不执行任何修改。" badge={resume.is_active ? <span className="stateBadge success">使用中</span> : <span className="stateBadge">已停用</span>} />
    <div className="detailLayout">
      <aside className="detailPanel detailAside">
        <span className="largeResourceIcon"><FileIcon /></span>
        <dl><div><dt>基础版本</dt><dd>V{resume.base_version}</dd></div><div><dt>父版本</dt><dd>{resume.parent_id ? `#${resume.parent_id}` : "无"}</dd></div><div><dt>创建时间</dt><dd>{formatDate(resume.created_at, "日期未知")}</dd></div><div><dt>当前状态</dt><dd>{resume.is_active ? "可用" : "停用"}</dd></div></dl>
      </aside>
      <section className="detailPanel" aria-labelledby="resume-content-title">
        <div className="panelHeading"><div><p className="eyebrow">证据内容</p><h2 id="resume-content-title">简历章节与经历</h2></div></div>
        <ResumeOutline data={resume.structured_json} />
      </section>
    </div>
  </div>;
}
