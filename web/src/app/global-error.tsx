"use client";

export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <html lang="zh-CN">
      <body>
        <main className="standaloneError">
          <span className="errorCode">页面异常</span>
          <h1>JobFun 遇到了一个问题</h1>
          <p>请重新加载页面。若问题持续存在，请保留当前时间并检查服务日志。</p>
          <button className="primaryButton compact" type="button" onClick={reset}>重新加载</button>
        </main>
      </body>
    </html>
  );
}
