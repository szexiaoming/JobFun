"use client";

import { FormEvent, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { ShieldIcon } from "@/components/icons";

export function LoginForm() {
  const [token, setToken] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const router = useRouter();
  const search = useSearchParams();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setMessage("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      const body = (await response.json()) as { error?: string };
      if (!response.ok) {
        setMessage(body.error || "登录失败，请稍后重试");
        return;
      }
      const requested = search.get("next") || "/dashboard";
      const destination = requested.startsWith("/dashboard") ? requested : "/dashboard";
      router.replace(destination);
      router.refresh();
    } catch {
      setMessage("无法连接客户端服务，请检查网络后重试");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="loginForm" method="post" onSubmit={submit}>
      <div className="fieldGroup">
        <label htmlFor="api-token">API Token</label>
        <div className="tokenField">
          <ShieldIcon />
          <input
            id="api-token"
            name="api-token"
            type="password"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="粘贴你的 JobFun API Token"
            autoComplete="current-password"
            spellCheck={false}
            required
            minLength={32}
            maxLength={512}
          />
        </div>
        <p className="fieldHint">Token 仅写入 HttpOnly Cookie，不保存在浏览器脚本存储中。</p>
      </div>
      {message && <p className="formError" role="alert">{message}</p>}
      <button className="primaryButton" type="submit" disabled={pending}>
        {pending ? "正在验证…" : "进入工作台"}
      </button>
    </form>
  );
}
