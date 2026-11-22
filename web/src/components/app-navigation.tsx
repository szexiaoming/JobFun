"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { AudioIcon, BriefcaseIcon, FileIcon, GridIcon, ShieldIcon } from "@/components/icons";

const items = [
  { label: "工作台", shortLabel: "工作台", href: "/dashboard", icon: GridIcon },
  { label: "简历", shortLabel: "简历", href: "/dashboard/resumes", icon: FileIcon },
  { label: "岗位", shortLabel: "岗位", href: "/dashboard/jobs", icon: BriefcaseIcon },
  { label: "申请", shortLabel: "申请", href: "/dashboard/applications", icon: ShieldIcon },
  { label: "音频", shortLabel: "音频", href: "/dashboard/audio", icon: AudioIcon },
];

export function AppNavigation({ mobile = false }: { mobile?: boolean }) {
  const pathname = usePathname();
  return (
    <nav className={mobile ? "bottomNav" : "sideNav"} aria-label={mobile ? "移动端导航" : "主要导航"}>
      {items.map(({ label, shortLabel, href, icon: Icon }) => {
        const current = href === "/dashboard" ? pathname === href : pathname.startsWith(href);
        return (
          <Link
            className={mobile ? (current ? "current" : "") : `navItem${current ? " active" : ""}`}
            href={href}
            aria-current={current ? "page" : undefined}
            key={href}
          >
            <Icon />
            {mobile ? <small>{shortLabel}</small> : label}
          </Link>
        );
      })}
    </nav>
  );
}
