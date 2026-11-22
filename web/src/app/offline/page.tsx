import type { Metadata } from "next";
import Link from "next/link";

import { Brand } from "@/components/brand";

export const metadata: Metadata = { title: "离线" };

export default function OfflinePage() {
  return (
    <main className="offlinePage" id="main-content">
      <Brand />
      <div>
        <span className="errorCode">当前离线</span>
        <h1>网络恢复后，再继续你的求职计划</h1>
        <p>为保护个人数据，JobFun 不会离线缓存 API 响应。已经打开的静态界面仍可使用。</p>
        <Link className="primaryButton compact" href="/dashboard">重试连接</Link>
      </div>
    </main>
  );
}
