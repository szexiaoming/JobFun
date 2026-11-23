import "server-only";

import { backendRequest } from "@/lib/server-api";
import type { GapRequirement } from "@/lib/client-api-types";

export type WorkbenchItem = {
  application_id: number;
  jd_id: number;
  company: string;
  position: string;
  status: string;
  next_step: string;
  next_step_due: string;
  interview_at: string;
  is_overdue: boolean;
};

export type Workbench = {
  total_applications: number;
  active_applications: number;
  pending_actions: WorkbenchItem[];
  overdue_actions: WorkbenchItem[];
  upcoming_interviews: WorkbenchItem[];
};

export type ResumeSummary = {
  id: number;
  name: string;
  base_version: number;
  parent_id: number | null;
  created_at: string;
  is_active: boolean;
};

export type ResumeDetail = ResumeSummary & {
  structured_json: Record<string, unknown>;
};

export type MatchSummary = {
  id: number;
  total_score: number;
  skill_score: number;
  experience_score: number;
  education_score: number;
  soft_skill_score: number;
  culture_score: number;
  matched_skills: unknown[];
  missing_skills: unknown[];
  risks: unknown[];
  created_at: string;
};

export type JobSummary = {
  id: number;
  company: string;
  position: string;
  source_type: string;
  source_url: string;
  created_at: string;
  match_count: number;
  application_count: number;
  latest_match: MatchSummary | null;
};

export type JobDetail = JobSummary & {
  raw_text: string;
  structured_json: Record<string, unknown>;
};

export type ApplicationSummary = {
  id: number;
  status: string;
  applied_date: string;
  next_step: string;
  next_step_due: string;
  interview_at: string;
  updated_at: string;
  job: { id: number; company: string; position: string; structured_json?: Record<string, unknown> | null };
  resume: { id: number; name: string; base_version: number; structured_json?: Record<string, unknown> | null };
  match: MatchSummary | null;
};

export type ApplicationDetail = ApplicationSummary & {
  notes: string;
};

export type InterviewQuestion = {
  id: number;
  category: string;
  question: string;
  difficulty: string;
  attempt_count: number;
  latest_attempt_id: number | null;
  latest_score: number | null;
};

export type InterviewInsights = {
  attempt_count: number;
  practiced_question_count: number;
  comparison_count: number;
  main_attempt_count: number;
  follow_up_attempt_count: number;
  overall_average: number;
  dimension_averages: Record<string, number>;
  dimension_changes: Record<string, number>;
  category_averages: Record<string, number>;
  weak_dimensions: string[];
  weak_categories: string[];
};

export type PageResult<T> = {
  items: T[];
  page: number;
  hasPrevious: boolean;
  hasNext: boolean;
};

export type RetainedAudio = {
  id: number;
  original_name: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
  expires_at: string;
};

export type RetainedAudioList = {
  items: RetainedAudio[];
  retention_days: number;
  maintenance: {
    status: "healthy" | "warning" | "degraded";
    task_status: string;
    last_completed_age_seconds: number | null;
    last_checked: number;
    last_deleted: number;
    last_failed: number;
    consecutive_failures: number;
    run_total: number;
    deleted_total: number;
    failed_total: number;
    checks: Record<string, string>;
    trend: {
      window_runs: number;
      success_rate_percent: number;
      checked_count: number;
      deleted_count: number;
      failed_count: number;
    };
    recent_runs: Array<{
      status: string;
      completed_at: string;
      checked_count: number;
      deleted_count: number;
      failed_count: number;
      error_code: string;
    }>;
  };
  retention_policy: {
    configured_days: number;
    observed_days: number | null;
    last_observed_at: string;
    changes: Array<{
      previous_days: number;
      new_days: number;
      changed_at: string;
      source: "configuration";
    }>;
  };
};

const PAGE_SIZE = 10;

export function getWorkbench(): Promise<Workbench> {
  return backendRequest<Workbench>("/workbench");
}

export function listRetainedAudio(): Promise<RetainedAudioList> {
  return backendRequest<RetainedAudioList>("/retained-audio");
}

export function listResumes(page: number): Promise<PageResult<ResumeSummary>> {
  return pagedRequest<ResumeSummary>("/resumes", page);
}

export function listJobs(page: number): Promise<PageResult<JobSummary>> {
  return pagedRequest<JobSummary>("/jobs", page);
}

export function listApplications(page: number): Promise<PageResult<ApplicationSummary>> {
  return pagedRequest<ApplicationSummary>("/applications", page);
}

export function getResume(id: number): Promise<ResumeDetail> {
  return backendRequest<ResumeDetail>(`/resumes/${id}`);
}

export function getJob(id: number): Promise<JobDetail> {
  return backendRequest<JobDetail>(`/jobs/${id}`);
}

export function getApplication(id: number): Promise<ApplicationDetail> {
  return backendRequest<ApplicationDetail>(`/applications/${id}`);
}

export function getApplicationRequirements(id: number): Promise<GapRequirement[]> {
  return backendRequest<GapRequirement[]>(`/applications/${id}/requirements`);
}

export function listInterviewQuestions(applicationId: number): Promise<InterviewQuestion[]> {
  return backendRequest<InterviewQuestion[]>(`/applications/${applicationId}/interview-questions`);
}

export function getInterviewInsights(applicationId: number): Promise<InterviewInsights> {
  return backendRequest<InterviewInsights>(`/applications/${applicationId}/interview-insights`);
}

export async function listMatchOptions(): Promise<{ resumes: ResumeSummary[]; jobs: JobSummary[] }> {
  const [resumes, jobs] = await Promise.all([
    backendRequest<ResumeSummary[]>("/resumes?limit=100&offset=0"),
    backendRequest<JobSummary[]>("/jobs?limit=100&offset=0"),
  ]);
  return { resumes, jobs };
}

export function safePage(value: string | string[] | undefined): number {
  const raw = Array.isArray(value) ? value[0] : value;
  const parsed = Number(raw);
  return Number.isSafeInteger(parsed) && parsed > 0 ? Math.min(parsed, 10_000) : 1;
}

async function pagedRequest<T>(path: string, page: number): Promise<PageResult<T>> {
  const offset = (page - 1) * PAGE_SIZE;
  const rows = await backendRequest<T[]>(`${path}?limit=${PAGE_SIZE + 1}&offset=${offset}`);
  return {
    items: rows.slice(0, PAGE_SIZE),
    page,
    hasPrevious: page > 1,
    hasNext: rows.length > PAGE_SIZE,
  };
}
