export interface Application {
  applicationId: string;
  applicantName: string;
  institution: string;
  country: string;
  submittedAt: string;
  ageHours: number;
  flagCount: number;
  highestSeverity: "High" | "Medium" | "Low" | null;
  status: string;
  caseRef: string | null;
  licenseNumber: string;
  originalFilename: string;
  programYear: string;
  pageCount: number;
}

export interface SourceLocation {
  page: number;
  spans: string[];
}

export interface Flag {
  ruleCode: string;
  ruleName: string;
  severity: "High" | "Medium" | "Low";
  rationale: string;
  sourceLocation: SourceLocation;
  status: string;
  safePractice: string;
}

export interface ExtractionRow {
  field: string;
  value: string;
  confidence: "high" | "medium" | "low";
  expected?: string;
}

export interface ExtractionData {
  physical: ExtractionRow[];
  content: ExtractionRow[];
  program: ExtractionRow[];
}

export interface AuditEvent {
  ts: string;
  actor: string;
  event: string;
  detail: string;
}

export interface FlagDecision {
  decision: "CONFIRM" | "OVERRIDE" | undefined;
  notes: string;
}

export type Decisions = Record<string, FlagDecision>;

export type OverallDecision =
  | "READY_FOR_LICENSING_REVIEW"
  | "RETURN_TO_APPLICANT"
  | "DENIED"
  | "DEFERRED"
  | null;
