import { createServer } from "node:http";

const resumeStructured = { sections: [
  { title: "工作经历", entries: [{ header: "Backend Engineer · Aurora Systems", bullets: ["设计 FastAPI 服务并将关键接口延迟降低 38%", "建立可追踪的任务队列和失败重试机制"] }] },
  { title: "项目经历", entries: [{ header: "JobFun · AI 求职工作台", bullets: ["实现证据优先的岗位匹配与申请闭环", "构建 Next.js PWA 与安全 HttpOnly 会话"] }] },
] };
const jobStructured = { company: "Northstar Labs", position: "Senior Backend Engineer", team: "Platform", location: "London / Hybrid", level: "Senior", years_experience: 5, education: "计算机相关专业本科", required_skills: ["Python", "FastAPI", "PostgreSQL", "AWS"], preferred_skills: ["Kubernetes", "Terraform"], soft_skills: ["跨团队沟通", "技术领导力"], culture_signals: ["Ownership", "Evidence-driven"], responsibilities: ["设计并维护高可用后端服务", "推动可观测性与工程质量", "指导团队完成关键技术决策"] };
const match = { id: 31, total_score: 86, skill_score: 88, experience_score: 84, education_score: 80, soft_skill_score: 90, culture_score: 85, matched_skills: ["Python", "FastAPI"], missing_skills: ["Kubernetes"], risks: [], created_at: "2026-11-18T10:00:00Z" };
const generatedMatch = { id: 33, total_score: 89, skill_score: 92, experience_score: 87, education_score: 82, soft_skill_score: 90, culture_score: 88, matched_skills: ["Python", "FastAPI", "PostgreSQL"], missing_skills: ["Kubernetes", "Terraform"], risks: ["需要补充大规模平台治理案例"], created_at: "2026-11-21T10:00:03Z" };
const resumes = [
  { id: 11, name: "后端工程师主简历", base_version: 3, parent_id: 8, created_at: "2026-11-16T10:00:00Z", is_active: true },
  { id: 8, name: "通用技术简历", base_version: 2, parent_id: null, created_at: "2026-10-29T10:00:00Z", is_active: true },
  { id: 5, name: "早期版本", base_version: 1, parent_id: null, created_at: "2026-09-12T10:00:00Z", is_active: false },
];
const jobs = [
  { id: 21, company: "Northstar Labs", position: "Senior Backend Engineer", source_type: "url", source_url: "https://example.com/job", created_at: "2026-11-18T10:00:00Z", match_count: 2, application_count: 1, latest_match: match },
  { id: 22, company: "栖云科技", position: "AI 产品工程师", source_type: "text", source_url: "", created_at: "2026-11-17T10:00:00Z", match_count: 1, application_count: 1, latest_match: { ...match, id: 32, total_score: 79 } },
  { id: 23, company: "Orbit Works", position: "Platform Developer", source_type: "file", source_url: "", created_at: "2026-11-15T10:00:00Z", match_count: 0, application_count: 0, latest_match: null },
];
const applications = [
  { id: 41, status: "interview", applied_date: "2026-11-18", next_step: "准备系统设计案例", next_step_due: "2026-11-23", interview_at: "2026-11-24T14:30:00Z", updated_at: "2026-11-20T10:00:00Z", job: { id: 21, company: "Northstar Labs", position: "Senior Backend Engineer" }, resume: { id: 11, name: "后端工程师主简历", base_version: 3 }, match },
  { id: 42, status: "screening", applied_date: "2026-11-17", next_step: "跟进招聘负责人", next_step_due: "2026-11-22", interview_at: "", updated_at: "2026-11-19T10:00:00Z", job: { id: 22, company: "栖云科技", position: "AI 产品工程师" }, resume: { id: 8, name: "通用技术简历", base_version: 2 }, match: { ...match, id: 32, total_score: 79 } },
];

const interviewQuestions = [
  { id: 91, match_id: 31, category: "system_design", question: "请介绍一次你主导高可用后端系统设计的经历，并说明关键权衡。", difficulty: "hard", attempt_count: 1, latest_attempt_id: 100, latest_score: 3.8 },
  { id: 92, match_id: 31, category: "project_deep_dive", question: "在 JobFun 项目中，你如何保证异步任务可追踪且失败后可以恢复？", difficulty: "medium", attempt_count: 0, latest_attempt_id: null, latest_score: null },
  { id: 93, match_id: 31, category: "behavioral", question: "请举例说明你如何推动一次跨团队技术决策。", difficulty: "medium", attempt_count: 0, latest_attempt_id: null, latest_score: null },
  { id: 94, match_id: 33, category: "technical", question: "如何定位并改善一个高并发 Python API 的尾延迟？", difficulty: "hard", attempt_count: 0, latest_attempt_id: null, latest_score: null },
];

const interviewAttempts = new Map();
const storedObjects = new Map();
const transcriptionDrafts = new Map();
storedObjects.set(80, { id: 80, object_key: "private/mock-retained-80", kind: "interview_audio", original_name: "system-design-answer.webm", content_type: "audio/webm", size_bytes: 428000, sha256: "b".repeat(64), status: "available", created_at: "2026-11-12T12:00:00Z", replayed: false, retained: true });
interviewAttempts.set(100, {
  id: 100, application_id: 41, question_id: 91, question: interviewQuestions[0].question, category: "system_design",
  answer_text: "我先从容量、故障域和恢复目标拆解系统，再用压测验证关键路径。",
  scores: { completeness: 3.8, truthfulness: 4.2, technical: 3.7, structure: 3.5 }, overall_score: 3.8,
  feedback: { summary: "思路清楚，但还可以补充量化结果。", strengths: ["说明了设计方法"], improvements: ["补充可用性目标和业务结果"], next_practice: "用一个真实项目按背景、权衡和结果重新组织。", unsupported_claims: [] },
  answer_mode: "text", audio_retained: false,
  created_at: "2026-11-20T10:00:00Z",
});

const operations = new Map();
let nextUploadId = 81;
let nextApplicationId = 43;

function operation(id, type, resultRefs, status = "queued", progress = 10) {
  return {
    id,
    operation_type: type,
    status,
    progress,
    input_refs: {},
    result_refs: resultRefs,
    error_code: status === "queued" ? "operation_retry_scheduled" : "",
    error_message: status === "queued" ? "操作暂未完成，已安排自动重试" : "",
    model: "mock-structured-model",
    input_units: 0,
    output_units: 0,
    estimated_cost: 0,
    retry_count: status === "queued" ? 1 : 0,
    created_at: "2026-11-21T10:00:00Z",
    started_at: "",
    completed_at: "",
    replayed: false,
  };
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1:8765");
  if (!request.headers.authorization?.startsWith("Bearer ")) return send(response, 401, { error: { code: "authentication_required", message: "invalid" } });
  if (["POST", "PATCH"].includes(request.method)) {
    if (!request.headers["idempotency-key"]) return send(response, 422, { error: { code: "missing_idempotency_key", message: "missing key" } });
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    let payload = {};
    if (request.headers["content-type"]?.startsWith("application/json")) {
      try { payload = JSON.parse(Buffer.concat(chunks).toString("utf8")); } catch { return send(response, 400, { error: { code: "invalid_json", message: "invalid json" } }); }
    }
    if (url.pathname === "/api/v1/resumes") {
      const queued = operation(71, "resume_parse", { resume_id: 11 });
      operations.set(queued.id, { value: queued, polls: 0 });
      return send(response, 202, queued);
    }
    if (url.pathname === "/api/v1/jobs") {
      const queued = operation(72, "jd_parse", { job_id: 21 });
      operations.set(queued.id, { value: queued, polls: 0 });
      return send(response, 202, queued);
    }
    if (url.pathname === "/api/v1/matches") {
      const resumeId = Number(payload.resume_id);
      const jobId = Number(payload.job_id);
      if (!resumes.some((item) => item.id === resumeId) || !jobs.some((item) => item.id === jobId)) return send(response, 404, { error: { code: "resource_not_found", message: "missing" } });
      const queued = { ...operation(73, "match", {}), input_refs: { resume_id: resumeId, job_id: jobId } };
      operations.set(queued.id, { value: queued, polls: 0, finalResultRefs: { match_id: generatedMatch.id } });
      return send(response, 202, queued);
    }
    if (request.method === "POST" && url.pathname === "/api/v1/applications") {
      const job = jobs.find((item) => item.id === Number(payload.job_id));
      const resume = resumes.find((item) => item.id === Number(payload.resume_id));
      const selectedMatch = [match, generatedMatch, { ...match, id: 32, total_score: 79 }].find((item) => item.id === Number(payload.match_id));
      if (!job || !resume || !selectedMatch) return send(response, 404, { error: { code: "resource_not_found", message: "missing" } });
      const created = {
        id: nextApplicationId++, status: "saved", applied_date: "", next_step: "", next_step_due: "", interview_at: "", updated_at: "2026-11-21T11:00:00Z", notes: String(payload.notes || ""),
        job: { id: job.id, company: job.company, position: job.position },
        resume: { id: resume.id, name: resume.name, base_version: resume.base_version },
        match: selectedMatch,
      };
      applications.push(created);
      return send(response, 201, { operation: operation(74, "application_create", { application_id: created.id }, "succeeded", 100), application: created });
    }
    const applicationUpdate = url.pathname.match(/^\/api\/v1\/applications\/(\d+)$/);
    if (request.method === "PATCH" && applicationUpdate) {
      const application = applications.find((item) => item.id === Number(applicationUpdate[1]));
      if (!application) return send(response, 404, { error: { code: "resource_not_found", message: "missing" } });
      if (payload.status) { application.status = String(payload.status); if (payload.status === "applied" && !application.applied_date) application.applied_date = "2026-11-21"; }
      if (payload.note) application.notes = `${application.notes || ""}\n${String(payload.note)}`.trim();
      if (payload.next_step !== undefined) application.next_step = String(payload.next_step);
      if (payload.next_step_due !== undefined) application.next_step_due = String(payload.next_step_due);
      if (payload.interview_at !== undefined) application.interview_at = String(payload.interview_at);
      application.updated_at = "2026-11-21T11:05:00Z";
      return send(response, 200, { operation: operation(75, "application_update", { application_id: application.id }, "succeeded", 100), application });
    }
    if (request.method === "POST" && url.pathname === "/api/v1/interview-attempts") {
      const application = applications.find((item) => item.id === Number(payload.application_id));
      const question = interviewQuestions.find((item) => item.id === Number(payload.question_id));
      if (!application || !question || application.match?.id !== question.match_id) return send(response, 404, { error: { code: "resource_not_found", message: "missing" } });
      const answerText = String(payload.answer_text || "").trim();
      if (!answerText) return send(response, 422, { error: { code: "validation_error", message: "answer required" } });
      const transcriptOperationId = Number(payload.transcription_operation_id || 0);
      const transcriptDraft = transcriptOperationId ? transcriptionDrafts.get(transcriptOperationId) : null;
      if (transcriptOperationId && (!transcriptDraft || transcriptDraft.application_id !== application.id || transcriptDraft.question_id !== question.id)) return send(response, 404, { error: { code: "resource_not_found", message: "missing" } });
      const attemptId = 101;
      const queued = { ...operation(76, "interview_answer", {}), input_refs: { application_id: application.id, question_id: question.id } };
      operations.set(queued.id, { value: queued, polls: 0, finalResultRefs: { attempt_id: attemptId }, pendingAttempt: {
        id: attemptId, application_id: application.id, question_id: question.id, question: question.question, category: question.category,
        answer_text: answerText, scores: { completeness: 4.1, truthfulness: 4.6, technical: 4.2, structure: 3.9 }, overall_score: 4.2,
        feedback: {
          summary: "回答基于真实项目证据，技术路径完整；如果把背景、个人贡献和结果分段，表达会更有说服力。",
          strengths: ["解释了异步任务的状态流转和自动重试", "明确区分了系统机制与个人负责部分"],
          improvements: ["补充失败率或恢复时长等量化指标", "先给结论，再展开实现细节"],
          next_practice: "用 90 秒重新回答，并补充一个可验证的恢复指标。",
          unsupported_claims: [], evidence_citations: ["JobFun 项目：任务队列和失败重试机制"],
        }, answer_mode: transcriptDraft ? "voice" : "text", audio_retained: Boolean(transcriptDraft?.audio_retained && payload.retain_audio), created_at: "2026-11-21T11:20:00Z",
      } });
      if (transcriptDraft) {
        if (!payload.retain_audio) storedObjects.delete(transcriptDraft.object_id);
        transcriptionDrafts.delete(transcriptOperationId);
      }
      return send(response, 202, queued);
    }
    if (request.method === "POST" && url.pathname === "/api/v1/interview-transcriptions") {
      const application = applications.find((item) => item.id === Number(payload.application_id));
      const question = interviewQuestions.find((item) => item.id === Number(payload.question_id));
      const stored = storedObjects.get(Number(payload.object_id));
      if (!application || !question || application.match?.id !== question.match_id || !stored || stored.kind !== "interview_audio") return send(response, 404, { error: { code: "resource_not_found", message: "missing" } });
      const queued = { ...operation(77, "interview_transcription", {}), input_refs: { application_id: application.id, question_id: question.id, object_id: stored.id, retain_audio: payload.retain_audio ? 1 : 0 } };
      operations.set(queued.id, { value: queued, polls: 0, finalResultRefs: { object_id: stored.id, draft_ready: 1 }, pendingDraft: {
        operation_id: queued.id, application_id: application.id, question_id: question.id, object_id: stored.id,
        transcript: "在 JobFun 项目中，我使用带用户归属的任务状态机、幂等键和有限重试，让每次失败与结果都可以追踪。",
        original_name: stored.original_name, content_type: stored.content_type, size_bytes: stored.size_bytes,
        audio_retained: Boolean(payload.retain_audio), expires_at: "2026-11-22T12:00:00Z",
      } });
      return send(response, 202, queued);
    }
    if (url.pathname === "/api/v1/uploads/resume_source" || url.pathname === "/api/v1/uploads/job_source") {
      const isResume = url.pathname.endsWith("resume_source");
      return send(response, 201, {
        id: nextUploadId++,
        object_key: "private/mock-object-key",
        kind: isResume ? "resume_source" : "job_source",
        original_name: isResume ? "candidate-resume.pdf" : "job-description.pdf",
        content_type: "application/pdf",
        size_bytes: 24576,
        sha256: "f".repeat(64),
        status: "stored",
        created_at: "2026-11-21T10:00:00Z",
        replayed: false,
      });
    }
    if (url.pathname === "/api/v1/uploads/interview_audio") {
      const id = nextUploadId++;
      const stored = { id, object_key: `private/mock-audio-${id}`, kind: "interview_audio", original_name: "jobfun-answer.webm", content_type: "audio/webm", size_bytes: 32000, sha256: "a".repeat(64), status: "available", created_at: "2026-11-21T12:00:00Z", replayed: false };
      storedObjects.set(id, stored);
      return send(response, 201, stored);
    }
    return send(response, 405, { error: { code: "method_not_allowed", message: "unsupported write" } });
  }
  if (request.method === "DELETE") {
    if (url.pathname === "/api/v1/retained-audio") {
      const chunks = [];
      for await (const chunk of request) chunks.push(chunk);
      let payload = {};
      try { payload = JSON.parse(Buffer.concat(chunks).toString("utf8")); } catch { return send(response, 400, { error: { code: "invalid_json", message: "invalid json" } }); }
      const ids = [...new Set(Array.isArray(payload.object_ids) ? payload.object_ids.map(Number) : [])];
      let deleted = 0;
      for (const id of ids) {
        const stored = storedObjects.get(id);
        if (stored?.retained) { storedObjects.delete(id); deleted += 1; }
      }
      return send(response, 200, { requested: ids.length, deleted, already_absent: ids.length - deleted });
    }
    const uploadDelete = url.pathname.match(/^\/api\/v1\/uploads\/(\d+)$/);
    if (!uploadDelete) return send(response, 405, { error: { code: "method_not_allowed", message: "unsupported" } });
    const objectId = Number(uploadDelete[1]);
    if (!storedObjects.has(objectId)) return send(response, 404, { error: { code: "resource_not_found", message: "missing" } });
    storedObjects.delete(objectId);
    return send(response, 200, { id: objectId, status: "deleted" });
  }
  if (request.method !== "GET") return send(response, 405, { error: { code: "method_not_allowed", message: "unsupported" } });
  if (url.pathname === "/api/v1/me") return send(response, 200, { id: 42, username: "demo-user", roles: ["member"] });
  if (url.pathname === "/api/v1/workbench") return send(response, 200, {
    total_applications: 2,
    active_applications: 2,
    pending_actions: [
      { application_id: 41, jd_id: 21, company: "Northstar Labs", position: "Senior Backend Engineer", status: "interview", next_step: "准备系统设计案例", next_step_due: "2026-11-23", interview_at: "2026-11-24T14:30:00Z", is_overdue: false },
      { application_id: 42, jd_id: 22, company: "栖云科技", position: "AI 产品工程师", status: "screening", next_step: "跟进招聘负责人", next_step_due: "2026-11-22", interview_at: "", is_overdue: true },
    ],
    overdue_actions: [{ application_id: 42, jd_id: 22, company: "栖云科技", position: "AI 产品工程师", status: "screening", next_step: "跟进招聘负责人", next_step_due: "2026-11-20", interview_at: "", is_overdue: true }],
    upcoming_interviews: [{ application_id: 41, jd_id: 21, company: "Northstar Labs", position: "Senior Backend Engineer", status: "interview", next_step: "准备系统设计案例", next_step_due: "2026-11-23", interview_at: "2026-11-24T14:30:00Z", is_overdue: false }],
  });
  if (url.pathname === "/api/v1/retained-audio") return send(response, 200, {
    retention_days: 30,
    maintenance: {
      status: "healthy", task_status: "succeeded", last_completed_age_seconds: 420,
      last_started_age_seconds: 425, last_checked: 3, last_deleted: 1, last_failed: 0,
      consecutive_failures: 0, run_total: 12, deleted_total: 8, failed_total: 0,
      checks: { schedule: "ok", runtime: "ok", failures: "ok" },
      trend: { window_runs: 3, success_rate_percent: 100, checked_count: 8, deleted_count: 3, failed_count: 0 },
      recent_runs: [
        { status: "succeeded", completed_at: "2026-11-21T11:53:00Z", checked_count: 3, deleted_count: 1, failed_count: 0, error_code: "" },
        { status: "succeeded", completed_at: "2026-11-20T12:00:00Z", checked_count: 4, deleted_count: 2, failed_count: 0, error_code: "" },
        { status: "succeeded", completed_at: "2026-11-19T12:00:00Z", checked_count: 1, deleted_count: 0, failed_count: 0, error_code: "" },
      ],
    },
    retention_policy: {
      configured_days: 30,
      observed_days: 30,
      last_observed_at: "2026-11-21T11:53:00Z",
      changes: [{ previous_days: 45, new_days: 30, changed_at: "2026-11-18T09:00:00Z", source: "configuration" }],
    },
    items: [...storedObjects.values()].filter((item) => item.retained).map((item) => ({
      id: item.id,
      original_name: item.original_name,
      content_type: item.content_type,
      size_bytes: item.size_bytes,
      created_at: item.created_at,
      expires_at: "2026-12-12T12:00:00Z",
    })),
  });
  if (url.pathname === "/api/v1/resumes") return send(response, 200, resumes);
  if (url.pathname === "/api/v1/jobs") return send(response, 200, jobs);
  if (url.pathname === "/api/v1/applications") return send(response, 200, applications);
  const operationStatus = url.pathname.match(/^\/api\/v1\/operations\/(\d+)$/);
  if (operationStatus) {
    const entry = operations.get(Number(operationStatus[1]));
    if (!entry) return send(response, 404, { error: { code: "resource_not_found", message: "missing" } });
    entry.polls += 1;
    if (entry.polls === 1) {
      entry.value = { ...entry.value, status: "running", progress: 58, error_code: "", error_message: "", started_at: "2026-11-21T10:00:01Z" };
    } else {
      entry.value = { ...entry.value, status: "succeeded", progress: 100, result_refs: entry.finalResultRefs || entry.value.result_refs, error_code: "", error_message: "", completed_at: "2026-11-21T10:00:03Z" };
      if (entry.value.operation_type === "match") {
        const job = jobs.find((item) => item.id === Number(entry.value.input_refs.job_id));
        if (job) { job.latest_match = generatedMatch; job.match_count += 1; }
      }
      if (entry.value.operation_type === "interview_answer" && entry.pendingAttempt) {
        interviewAttempts.set(entry.pendingAttempt.id, entry.pendingAttempt);
        const question = interviewQuestions.find((item) => item.id === entry.pendingAttempt.question_id);
        if (question) { question.attempt_count += 1; question.latest_attempt_id = entry.pendingAttempt.id; question.latest_score = entry.pendingAttempt.overall_score; }
        entry.pendingAttempt = null;
      }
      if (entry.value.operation_type === "interview_transcription" && entry.pendingDraft) {
        transcriptionDrafts.set(entry.value.id, entry.pendingDraft);
        if (!entry.pendingDraft.audio_retained) storedObjects.delete(entry.pendingDraft.object_id);
        entry.pendingDraft = null;
      }
    }
    return send(response, 200, entry.value);
  }
  const resumeDetail = url.pathname.match(/^\/api\/v1\/resumes\/(\d+)$/);
  if (resumeDetail) {
    const resume = resumes.find((item) => item.id === Number(resumeDetail[1]));
    return resume ? send(response, 200, { ...resume, structured_json: resumeStructured }) : send(response, 404, { error: { code: "resource_not_found", message: "missing" } });
  }
  const jobDetail = url.pathname.match(/^\/api\/v1\/jobs\/(\d+)$/);
  if (jobDetail) {
    const job = jobs.find((item) => item.id === Number(jobDetail[1]));
    return job ? send(response, 200, { ...job, raw_text: "Senior Backend Engineer\nBuild reliable Python services and lead platform improvements.", structured_json: { ...jobStructured, company: job.company, position: job.position } }) : send(response, 404, { error: { code: "resource_not_found", message: "missing" } });
  }
  const applicationDetail = url.pathname.match(/^\/api\/v1\/applications\/(\d+)$/);
  if (applicationDetail) {
    const application = applications.find((item) => item.id === Number(applicationDetail[1]));
    return application ? send(response, 200, { ...application, notes: application.notes ?? "招聘负责人建议重点准备系统设计和可靠性案例。", job: { ...application.job, structured_json: jobStructured }, resume: { ...application.resume, structured_json: resumeStructured } }) : send(response, 404, { error: { code: "resource_not_found", message: "missing" } });
  }
  const applicationQuestions = url.pathname.match(/^\/api\/v1\/applications\/(\d+)\/interview-questions$/);
  if (applicationQuestions) {
    const application = applications.find((item) => item.id === Number(applicationQuestions[1]));
    if (!application) return send(response, 404, { error: { code: "resource_not_found", message: "missing" } });
    return send(response, 200, interviewQuestions.filter((item) => item.match_id === application.match?.id).map((item) => ({ id: item.id, category: item.category, question: item.question, difficulty: item.difficulty, attempt_count: item.attempt_count, latest_attempt_id: item.latest_attempt_id, latest_score: item.latest_score })));
  }
  const applicationInsights = url.pathname.match(/^\/api\/v1\/applications\/(\d+)\/interview-insights$/);
  if (applicationInsights) {
    const application = applications.find((item) => item.id === Number(applicationInsights[1]));
    if (!application) return send(response, 404, { error: { code: "resource_not_found", message: "missing" } });
    const attempts = [...interviewAttempts.values()].filter((item) => item.application_id === application.id);
    const average = attempts.length ? attempts.reduce((sum, item) => sum + item.overall_score, 0) / attempts.length : 0;
    return send(response, 200, { attempt_count: attempts.length, practiced_question_count: new Set(attempts.map((item) => item.question_id)).size, comparison_count: 0, main_attempt_count: attempts.length, follow_up_attempt_count: 0, overall_average: Number(average.toFixed(2)), dimension_averages: {}, dimension_changes: {}, category_averages: {}, weak_dimensions: [], weak_categories: [] });
  }
  const interviewAttemptDetail = url.pathname.match(/^\/api\/v1\/interview-attempts\/(\d+)$/);
  if (interviewAttemptDetail) {
    const attempt = interviewAttempts.get(Number(interviewAttemptDetail[1]));
    return attempt ? send(response, 200, attempt) : send(response, 404, { error: { code: "resource_not_found", message: "missing" } });
  }
  const transcriptionDetail = url.pathname.match(/^\/api\/v1\/interview-transcriptions\/(\d+)$/);
  if (transcriptionDetail) {
    const draft = transcriptionDrafts.get(Number(transcriptionDetail[1]));
    return draft ? send(response, 200, draft) : send(response, 404, { error: { code: "resource_not_found", message: "missing" } });
  }
  return send(response, 404, { error: { code: "resource_not_found", message: "missing" } });
});

function send(response, status, body) {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(body));
}

server.listen(8765, "127.0.0.1", () => console.log("Mock JobFun API ready at http://127.0.0.1:8765"));
