"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { LogoutIcon } from "@/components/icons";

export function LogoutButton() {
  const [pending, setPending] = useState(false);
  const router = useRouter();

  async function signOut() {
    setPending(true);
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      router.replace("/login");
      router.refresh();
    }
  }

  return (
    <button className="logoutButton" onClick={signOut} disabled={pending} type="button">
      <LogoutIcon />
      <span>{pending ? "正在退出" : "退出登录"}</span>
    </button>
  );
}
