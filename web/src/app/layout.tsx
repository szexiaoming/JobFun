import type { Metadata, Viewport } from "next";

import { PwaRegister } from "@/components/pwa-register";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "JobFun · AI 求职工作台",
    template: "%s · JobFun",
  },
  description: "用可追溯的 AI 证据链管理简历、岗位匹配、申请与面试练习。",
  applicationName: "JobFun",
  manifest: "/manifest.webmanifest",
  icons: [{ rel: "icon", url: "/icon.svg", type: "image/svg+xml" }],
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#0b1530",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <a className="skipLink" href="#main-content">跳到主要内容</a>
        {children}
        <PwaRegister />
      </body>
    </html>
  );
}
