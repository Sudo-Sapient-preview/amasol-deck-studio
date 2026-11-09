export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";
export type StageStatus = "pending" | "running" | "done" | "failed" | "skipped";

export interface Stage {
  key: string;
  label: string;
  status: StageStatus;
  summary: string | null;
  started_at?: number;
  ended_at?: number;
}

export interface ReportSlide {
  n: number;
  kind: "cover" | "agenda" | "divider" | "content" | "closing";
  layout: string | null;
  visual: string;
  title?: string;
  id?: string;
  purpose?: string;
  flags?: string[];
  plan_reason?: string;
  plan_visual?: string;
  visual_change?: string;
}

export interface Report {
  title: string;
  subtitle: string;
  audience: string;
  goal: string;
  language: string;
  input_type: string;
  input_reason: string;
  assumed: string[];
  edits: string[];
  flagged: string[];
  intake_report: string;
  slides: ReportSlide[];
  plan: {
    infographics: number;
    cap: number | null;
    short_pitch: boolean;
    waive: Record<string, string>;
    cut: { id?: string; wanted?: string; now?: string; reason?: string }[];
    no_chart: { source_ref?: string; reason?: string }[];
    excluded: { quote?: string; reason?: string }[];
    chapters: string[];
  };
  layout_counts: Record<string, number>;
  verify: {
    result: "PASS" | "FAIL";
    passed: number | null;
    failed: number | null;
    skipped: number | null;
    notes: string[];
    lines: string[];
  };
  stage_summaries: Record<string, string>;
  warnings: string[];
  font_note: string;
}

export interface JobResult {
  pptx: string;
  pdf: string | null;
  slides: string[];
  slides_hd?: string[];
  contact: string | null;
  slide_count: number;
  report: Report;
  duration: number;
  usage: Usage;
  overrides?: {
    total: number;
    per_rule: Record<string, number>;
    rules: { text: string; italic?: boolean; bold?: boolean; underline?: boolean }[];
  } | null;
  unchanged?: boolean;
}

export interface Usage {
  input: number;
  output: number;
  cache_read: number;
  cache_write: number;
  calls: number;
}

export interface Job {
  id: string;
  created_at: number;
  updated_at: number;
  started_at?: number;
  finished_at?: number;
  status: JobStatus;
  error: string | null;
  brief: string;
  options: DeckOptions;
  model: string;
  title: string;
  parent_id: string | null;
  root_id: string;
  version: number;
  feedback: string | null;
  stages: Stage[];
  files: { name: string; role: string; bytes: number }[];
  warnings: string[];
  usage: Partial<Usage>;
  result: JobResult | null;
  content_chars?: number;
  brief_chars?: number;
}

export interface JobSummary {
  id: string;
  created_at: number;
  status: JobStatus;
  title: string;
  version: number;
  root_id: string;
  parent_id: string | null;
  model: string;
  slides: number | null;
  snippet: string;
}

export type LogKind = "info" | "agent" | "tool" | "ok" | "warn" | "error" | "note";

export interface JobEvent {
  seq: number;
  t: number;
  type: "log" | "stage" | "status";
  kind?: LogKind;
  text?: string;
  key?: string;
  status?: string;
  summary?: string | null;
  error?: string;
}

export interface DeckOptions {
  language?: "en" | "de";
  length?: number;
  format?: "short" | "full";
  audience?: string;
  goal?: string;
  presenter?: string;
  instructions?: string;
  review?: boolean;
}

export interface ModelInfo {
  id: string;
  label: string;
  hint: string;
}

export interface AppConfig {
  models: ModelInfo[];
  default_model: string;
  limits: { file_mb: number; total_mb: number; files: number };
}

export type FileRole = "content" | "reference" | "auto";

export interface PickedFile {
  key: string;
  file: File;
  path: string;
  role: FileRole;
}
