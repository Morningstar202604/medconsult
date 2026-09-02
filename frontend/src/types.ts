// 共享类型定义
export interface Skill {
  id: number;
  name: string;
  desc: string;
  prompt: string;
  active: boolean;
}

export interface Doc {
  id: number;
  name: string;
  size: number;
  ext: string;
  created_at?: string;
}

export interface Patient {
  id: number;
  name: string;
  gender: string;
  birth_date: string;
  hospital_no: string;
  id_card: string;
  phone: string;
  created_at?: string;
}

export interface Encounter {
  id: number;
  patient_id: number;
  visit_no: string;
  chief_complaint: string;
  history: string;
  meds: string;
  exams: string;
  vitals: string;
}

export interface ConsultationItem {
  id: number;
  title: string;
  mode: string;
  status: string;
  is_demo: boolean;
  data_completeness: string;
  created_at?: string;
}

export interface ConsultationDetail extends ConsultationItem {
  error_msg: string;
  specialties: string[];
  report: Report | null;
  events: EventItem[];
  evidence: EvidenceItem[];
  tool_calls: ToolCall[];
}

export interface EventItem {
  role: string;
  name: string;
  emoji: string;
  round: number;
  text: string;
}

export interface Report {
  final_diagnosis: string;
  confidence: string;
  recommended_dept: string;
  key_findings: string[];
  plan: string[];
  red_flags: string[];
  disagreements: string;
  warnings: string;
  calculations?: string[];
  data_completeness?: string;
  missing_info?: string;
  is_demo?: boolean;
  exam_suggestions?: string;
  drug_interactions?: string;
  dispute_detail?: { topic: string; type: string; for: string[]; against: string[]; summary: string }[];
  patient_report?: {
    summary: string;
    what_it_may_be: string;
    what_to_do: string[];
    when_to_seek_care: string[];
    questions_to_ask: string[];
    is_demo: boolean;
  };
}

export interface FeedbackItem {
  id: number;
  title: string;
  diagnosis: string;
  helpful: boolean;
  note: string;
  status: string;
  consultation_id: number | null;
  submitted_by: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string | null;
}

// ---- 证据链 / 工具审计 ----
export interface EvidenceItem {
  id: number;
  claim: string;
  basis_type: string;
  source: string;
  confidence: string;
  limitation: string;
}
export interface ToolCall {
  id: number;
  tool_name: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  confidence: string;
  note: string;
}

// ---- 问诊采集 ----
export interface IntakeQuestion {
  field: string;
  question: string;
  reason: string;
  priority: number;
  options?: string[];
}
export interface IntakeAnswerResp {
  reply: string | null;
  interrupt: boolean;
  red_flags: { severity: string; message: string; matched: string }[];
  done: boolean;
  next_question: IntakeQuestion | null;
  progress: { answered: number; total: number };
  status: string;
}

export interface MediaAsset {
  id: number;
  kind: "image" | "audio";
  filename: string;
  size_bytes: number;
  mime_type: string;
  engine: string;
  confidence: string;
  error_msg: string;
  text: string;
  consultation_id: number | null;
  intake_session_id: number | null;
  created_at: string | null;
  lines?: { text: string; score: number }[];
  segments?: { start: number; end: number; text: string }[];
  duration?: number;
}
