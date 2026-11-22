import type { Metadata } from "next";
import { Suspense } from "react";

import { Brand } from "@/components/brand";
import { ShieldIcon, SparkIcon } from "@/components/icons";
import { LoginForm } from "@/components/login-form";

export const metadata: Metadata = { title: "登录" };

export default function LoginPage() {
  return (
    <main className="loginPage" id="main-content">
      <section className="loginStory" aria-labelledby="login-title">
        <Brand />
        <div className="storyContent">
          <p className="eyebrow"><SparkIcon /> 证据优先的 AI 求职助手</p>
          <h1 id="login-title">
            <span>让每一次求职动作，</span>
            <span>都有依据可追溯。</span>
          </h1>
          <p className="storyLead">
            <span>从简历证据到岗位匹配，</span>
            <span>再到申请推进与面试复盘，</span>
            <span>JobFun 把分散的准备工作放进一个清晰闭环。</span>
          </p>
          <div className="principleCard">
            <ShieldIcon />
            <div>
              <strong>不编造，是第一原则</strong>
              <span className="principleText">
                <span>AI 只优化你已有的真实经历，</span>
                <span>关键修改始终由你确认。</span>
              </span>
            </div>
          </div>
        </div>
        <p className="storyFoot">JobFun Web · Iteration 0.37</p>
      </section>
      <section className="loginPanel" aria-label="登录表单">
        <div className="loginCard">
          <div className="mobileBrand"><Brand /></div>
          <p className="eyebrow">欢迎回来</p>
          <h2>登录 JobFun</h2>
          <p className="loginIntro">使用本地 API 签发的可撤销 Token，连接你的求职工作台。</p>
          <Suspense fallback={<div className="formSkeleton" aria-label="正在加载登录表单" />}>
            <LoginForm />
          </Suspense>
          <div className="loginHelp">
            <span>还没有 Token？</span>
            <code>python -m src.api.provision_token --user-id 1</code>
          </div>
        </div>
      </section>
    </main>
  );
}
