import type { Metadata } from "next";
import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { FileIcon } from "@/components/icons";
import { PageHeader } from "@/components/page-header";
import { Pagination } from "@/components/pagination";
import { listResumes, safePage } from "@/lib/jobfun-api";
import { formatDate } from "@/lib/presentation";

export const metadata: Metadata = { title: "简历" };
export default async function ResumesPage({ searchParams }: { searchParams: Promise<{ page?: string | string[] }> }) {
  const page = safePage((await searchParams).page);
  const result = await listResumes(page);
  return <div className="dashboardContent">
    <PageHeader eyebrow="简历中心" title="你的真实经历版本" description="查看简历版本与启用状态；任何 AI 解析都以你提交的真实内容为依据。" aside={<Link className="primaryButton compact" href="/dashboard/resumes/new">导入简历</Link>} />
    {result.items.length === 0 ? <EmptyState title={page > 1 ? "这一页没有简历" : "还没有简历"} description={page > 1 ? "请返回上一页继续查看。" : "导入第一份简历后，版本会集中显示在这里。"} icon={<FileIcon />} /> :
      <section className="cardGrid" aria-label="简历列表">{result.items.map((resume) => <Link className="resourceCard resourceLink" href={`/dashboard/resumes/${resume.id}`} key={resume.id}>
        <div className="resourceTop"><span className="resourceIcon"><FileIcon /></span>{resume.is_active ? <span className="stateBadge success">使用中</span> : <span className="stateBadge">已停用</span>}</div>
        <div><h2>{resume.name}</h2><p>版本 {resume.base_version}{resume.parent_id ? ` · 源自 #${resume.parent_id}` : " · 基础版本"}</p></div>
        <footer><span>简历 #{resume.id}</span><time>{formatDate(resume.created_at, "日期未知")}</time></footer>
      </Link>)}</section>}
    <Pagination {...result} />
  </div>;
}
