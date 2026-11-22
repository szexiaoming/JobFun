import Link from "next/link";

export default function NotFound() {
  return (
    <main className="standaloneError" id="main-content">
      <span className="errorCode">404</span>
      <h1>这里没有你要找的页面</h1>
      <p>链接可能已经变化，返回工作台继续你的求职计划。</p>
      <Link className="primaryButton compact" href="/dashboard">返回工作台</Link>
    </main>
  );
}
