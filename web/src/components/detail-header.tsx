import Link from "next/link";
import type { ReactNode } from "react";

export function DetailHeader({ backHref, backLabel, eyebrow, title, description, badge }: { backHref: string; backLabel: string; eyebrow: string; title: string; description: string; badge?: ReactNode }) {
  return (
    <header className="detailHeader">
      <Link className="backLink" href={backHref}>{backLabel}</Link>
      <div className="detailTitleRow">
        <div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p></div>
        {badge}
      </div>
    </header>
  );
}
