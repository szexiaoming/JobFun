"use client";

import { useEffect } from "react";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("dashboard_render_failed", error.digest || error.name);
  }, [error]);
  return (
    <section className="errorPanel" aria-labelledby="dashboard-error-title">
      <span className="errorCode">连接中断</span>
      <h1 id="dashboard-error-title">工作台暂时无法加载</h1>
      <p>你的数据没有被修改。请确认 JobFun API 正在运行，然后重新尝试。</p>
      <button className="primaryButton compact" type="button" onClick={reset}>重新加载</button>
    </section>
  );
}
