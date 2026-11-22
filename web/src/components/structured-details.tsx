type UnknownRecord = Record<string, unknown>;

export function ResumeOutline({ data, compact = false }: { data: UnknownRecord | null | undefined; compact?: boolean }) {
  const sections = Array.isArray(data?.sections) ? data.sections.map(asRecord).filter(Boolean) as UnknownRecord[] : [];
  if (!sections.length) return <p className="panelHint">这份简历暂时没有可读取的结构化章节。</p>;
  return <div className={`resumeOutline${compact ? " compact" : ""}`}>{sections.map((section, sectionIndex) => {
    const entries = Array.isArray(section.entries) ? section.entries.map(asRecord).filter(Boolean) as UnknownRecord[] : [];
    return <section key={`${text(section.title, "简历章节")}-${sectionIndex}`}><h3>{text(section.title, "简历章节")}</h3>{entries.length ? entries.map((entry, entryIndex) => {
      const bullets = stringList(entry.bullets);
      return <article key={`${text(entry.header, "经历")}-${entryIndex}`}><h4>{text(entry.header, "经历")}</h4>{bullets.length ? <ul>{bullets.map((bullet, bulletIndex) => <li key={`${bullet}-${bulletIndex}`}>{bullet}</li>)}</ul> : <p>没有可读取的要点。</p>}</article>;
    }) : <p>本章节还没有条目。</p>}</section>;
  })}</div>;
}

export function JobRequirements({ data }: { data: UnknownRecord | null | undefined }) {
  const groups = [
    ["必备技能", stringList(data?.required_skills)],
    ["加分技能", stringList(data?.preferred_skills)],
    ["软技能", stringList(data?.soft_skills)],
    ["文化信号", stringList(data?.culture_signals)],
  ] as const;
  const responsibilities = stringList(data?.responsibilities);
  return <div className="jobRequirements">
    <dl className="factGrid">
      <div><dt>职级</dt><dd>{text(data?.level, "未注明")}</dd></div>
      <div><dt>地点</dt><dd>{text(data?.location, "未注明")}</dd></div>
      <div><dt>团队</dt><dd>{text(data?.team, "未注明")}</dd></div>
      <div><dt>经验要求</dt><dd>{experience(data?.years_experience)}</dd></div>
      <div className="wide"><dt>教育要求</dt><dd>{text(data?.education, "未注明")}</dd></div>
    </dl>
    {groups.map(([title, values]) => <section className="tagSection" key={title}><h3>{title}</h3>{values.length ? <ul>{values.map((value, index) => <li key={`${value}-${index}`}>{value}</li>)}</ul> : <p>未注明</p>}</section>)}
    <section className="responsibilitySection"><h3>岗位职责</h3>{responsibilities.length ? <ul>{responsibilities.map((value, index) => <li key={`${value}-${index}`}>{value}</li>)}</ul> : <p>未提取到岗位职责。</p>}</section>
  </div>;
}

function asRecord(value: unknown): UnknownRecord | null { return value && typeof value === "object" && !Array.isArray(value) ? value as UnknownRecord : null; }
function stringList(value: unknown): string[] { return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())) : []; }
function text(value: unknown, fallback: string): string { return typeof value === "string" && value.trim() ? value : fallback; }
function experience(value: unknown): string { return typeof value === "number" && Number.isFinite(value) ? `${value}+ 年` : "未注明"; }
