import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { BriefcaseIcon, MessageIcon, ShieldIcon, SparkIcon } from "@/components/icons";
import { PageHeader } from "@/components/page-header";
import { getWorkbench, type WorkbenchItem } from "@/lib/jobfun-api";
import { formatDate, formatDateTime, statusLabel } from "@/lib/presentation";

export const metadata: Metadata = { title: "工作台" };

export default async function DashboardPage() {
  const workbench = await getWorkbench();
  const hasActivity = workbench.pending_actions.length > 0 || workbench.upcoming_interviews.length > 0;
  return (
    <div className="dashboardContent">
      <PageHeader eyebrow="求职工作台" title="今天从最重要的行动开始" description="把申请、下一步和面试安排集中在一个可信的只读视图里。" aside={<span className="connectionBadge"><span /> 数据已同步</span>} />
      <section className="metricGrid" aria-label="申请概况">
        <article><span className="metricIcon blue"><BriefcaseIcon /></span><div><strong>{workbench.total_applications}</strong><span>全部申请</span></div></article>
        <article><span className="metricIcon mint"><SparkIcon /></span><div><strong>{workbench.active_applications}</strong><span>进行中</span></div></article>
        <article><span className="metricIcon amber"><ShieldIcon /></span><div><strong>{workbench.pending_actions.length}</strong><span>待办行动</span></div></article>
        <article><span className="metricIcon purple"><MessageIcon /></span><div><strong>{workbench.upcoming_interviews.length}</strong><span>即将面试</span></div></article>
      </section>
      {workbench.overdue_actions.length > 0 && (
        <section className="contentSection alertSection" aria-labelledby="overdue-title">
          <div className="sectionHeading compact"><div><p className="eyebrow">需要关注</p><h2 id="overdue-title">已逾期的行动</h2></div><span>{workbench.overdue_actions.length} 项</span></div>
          <div className="actionList">{workbench.overdue_actions.map((item) => <ActionRow item={item} overdue key={item.application_id} />)}</div>
        </section>
      )}
      {!hasActivity && workbench.overdue_actions.length === 0 ? (
        <EmptyState title="工作台暂时很轻松" description="创建申请并设置下一步后，行动提醒和面试安排会出现在这里。" />
      ) : (
        <div className="workbenchColumns">
          <section className="contentSection" aria-labelledby="actions-title">
            <div className="sectionHeading compact"><div><p className="eyebrow">下一步</p><h2 id="actions-title">待办行动</h2></div><span>{workbench.pending_actions.length} 项</span></div>
            {workbench.pending_actions.length ? <div className="actionList">{workbench.pending_actions.map((item) => <ActionRow item={item} key={item.application_id} />)}</div> : <EmptyState title="暂无待办" description="所有行动都已处理。" />}
          </section>
          <section className="contentSection" aria-labelledby="interviews-title">
            <div className="sectionHeading compact"><div><p className="eyebrow">近期安排</p><h2 id="interviews-title">即将面试</h2></div><span>{workbench.upcoming_interviews.length} 场</span></div>
            {workbench.upcoming_interviews.length ? <div className="actionList">{workbench.upcoming_interviews.map((item) => <ActionRow item={item} interview key={item.application_id} />)}</div> : <EmptyState title="暂无面试" description="安排面试后会显示在这里。" icon={<MessageIcon />} />}
          </section>
        </div>
      )}
    </div>
  );
}

function ActionRow({ item, overdue = false, interview = false }: { item: WorkbenchItem; overdue?: boolean; interview?: boolean }) {
  const when = interview ? formatDateTime(item.interview_at) : formatDate(item.next_step_due);
  return (
    <Link className="actionRow actionLink" href={`/dashboard/applications/${item.application_id}`}>
      <span className={`actionMark${overdue ? " overdue" : ""}`} aria-hidden="true" />
      <div className="actionBody"><strong>{item.position}</strong><span>{item.company} · {statusLabel(item.status)}</span><p>{interview ? "面试安排" : item.next_step || "确认下一步"}</p></div>
      <time>{when}</time>
    </Link>
  );
}
