import { redirect } from "next/navigation";

import { AppNavigation } from "@/components/app-navigation";
import { Brand } from "@/components/brand";
import { LogoutButton } from "@/components/logout-button";
import { BackendError, getCurrentUser } from "@/lib/server-api";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  let user;
  try {
    user = await getCurrentUser();
  } catch (error) {
    if (error instanceof BackendError && error.status === 401) redirect("/login");
    throw error;
  }

  return (
    <div className="appShell">
      <aside className="sidebar">
        <Brand />
        <AppNavigation />
        <div className="sidebarFoot">
          <div className="userBlock">
            <span className="avatar" aria-hidden="true">{user.username.slice(0, 1).toUpperCase()}</span>
            <span><strong>{user.username}</strong><small>用户 #{user.id}</small></span>
          </div>
          <LogoutButton />
        </div>
      </aside>
      <div className="appStage">
        <header className="mobileHeader">
          <Brand compact />
          <span className="mobileUser">{user.username}</span>
        </header>
        <main className="dashboardMain" id="main-content">{children}</main>
        <AppNavigation mobile />
      </div>
    </div>
  );
}
