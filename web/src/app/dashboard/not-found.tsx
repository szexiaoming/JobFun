import Link from "next/link";

export default function DashboardNotFound() {
  return <div className="errorPanel"><span className="errorCode">404 · Not Found</span><h1>没有找到这条记录</h1><p>它可能已被删除、编号无效，或者不属于当前账户。</p><Link className="primaryButton compact" href="/dashboard">返回工作台</Link></div>;
}
