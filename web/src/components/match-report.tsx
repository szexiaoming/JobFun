import { score } from "@/lib/presentation";
import type { MatchSummary } from "@/lib/jobfun-api";

const dimensions: Array<{ key: keyof MatchSummary; label: string }> = [
  { key: "skill_score", label: "技能" },
  { key: "experience_score", label: "经验" },
  { key: "education_score", label: "教育" },
  { key: "soft_skill_score", label: "软技能" },
  { key: "culture_score", label: "文化契合" },
];

export function MatchReport({ match }: { match: MatchSummary | null }) {
  if (!match) return <section className="detailPanel"><div className="panelHeading"><div><p className="eyebrow">匹配报告</p><h2>尚未生成匹配</h2></div></div><p className="panelHint">当前岗位和简历之间还没有可读取的匹配结果。</p></section>;
  return (
    <section className="detailPanel" aria-labelledby="match-report-title">
      <div className="matchLead"><div><p className="eyebrow">匹配报告 #{match.id}</p><h2 id="match-report-title">五维岗位匹配</h2><p>分数只基于简历中已有的证据，不代表录用概率。</p></div><strong>{score(match.total_score)}</strong></div>
      <div className="scoreList">
        {dimensions.map(({ key, label }) => {
          const value = Number(match[key]) || 0;
          return <div className="scoreRow" key={key}><span>{label}</span><div><i style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div><strong>{score(value)}</strong></div>;
        })}
      </div>
      <div className="matchLists">
        <MatchList title="已有证据" values={match.matched_skills} tone="positive" empty="暂未识别到明确匹配项" />
        <MatchList title="能力差距" values={match.missing_skills} tone="warning" empty="没有记录明确缺口" />
        <MatchList title="风险提示" values={match.risks} tone="risk" empty="没有记录额外风险" />
      </div>
    </section>
  );
}

function MatchList({ title, values, tone, empty }: { title: string; values: unknown[]; tone: string; empty: string }) {
  const readable = values.map(toText).filter(Boolean);
  return <div className="matchList"><h3>{title}</h3>{readable.length ? <ul>{readable.map((value, index) => <li className={tone} key={`${value}-${index}`}>{value}</li>)}</ul> : <p>{empty}</p>}</div>;
}

function toText(value: unknown): string {
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["name", "skill", "text", "description", "title"]) {
      if (typeof record[key] === "string") return record[key] as string;
    }
  }
  return "";
}
