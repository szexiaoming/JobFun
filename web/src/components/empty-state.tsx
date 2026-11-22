import type { ReactNode } from "react";

import { SparkIcon } from "@/components/icons";

export function EmptyState({ title, description, icon }: { title: string; description: string; icon?: ReactNode }) {
  return (
    <div className="emptyState">
      <span className="emptyIcon">{icon ?? <SparkIcon />}</span>
      <h2>{title}</h2>
      <p>{description}</p>
    </div>
  );
}
