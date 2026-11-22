export type OperationStatus = "queued" | "running" | "succeeded" | "failed";

export type Operation = {
  id: number;
  operation_type: string;
  status: OperationStatus;
  progress: number;
  input_refs: Record<string, number>;
  result_refs: Record<string, number>;
  error_code: string;
  error_message: string;
  model: string;
  input_units: number;
  output_units: number;
  estimated_cost: number;
  retry_count: number;
  created_at: string;
  started_at: string;
  completed_at: string;
  replayed: boolean;
};

export type StoredObject = {
  id: number;
  kind: "resume_source" | "job_source" | "interview_audio";
  original_name: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  status: string;
  created_at: string;
  replayed: boolean;
};

export type MatchResumeOption = {
  id: number;
  name: string;
  base_version: number;
  is_active: boolean;
};

export type MatchJobOption = {
  id: number;
  company: string;
  position: string;
  match_count: number;
  latest_score: number | null;
};

export type ApplicationMutationResult = {
  operation: Operation;
  application: {
    id: number;
    status: string;
    applied_date: string;
    next_step: string;
    next_step_due: string;
    interview_at: string;
    notes: string;
  };
};

export type InterviewAttemptDetail = {
  id: number;
  question_id: number;
  application_id: number;
  question: string;
  category: string;
  answer_text: string;
  scores: Record<string, number>;
  overall_score: number;
  feedback: Record<string, unknown>;
  answer_mode: "text" | "voice";
  audio_retained: boolean;
  created_at: string;
};

export type InterviewTranscriptionDraft = {
  operation_id: number;
  application_id: number;
  question_id: number;
  object_id: number;
  transcript: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
  audio_retained: boolean;
  expires_at: string;
};
