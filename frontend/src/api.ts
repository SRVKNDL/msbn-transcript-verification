import type { Application, Flag, ExtractionData, AuditEvent } from "./types";
import { getIdToken } from "./auth";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function fetchJson<T>(path: string): Promise<T> {
  requireApiBase();
  const headers = await authHeaders();
  const res = await fetch(`${API_BASE}${path}`, { headers });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

async function authHeaders() {
  const token = await getIdToken();
  return token ? { Authorization: `Bearer ${token}` } : undefined;
}

function requireApiBase() {
  if (!API_BASE) {
    throw new Error("VITE_API_BASE is required. Production data cannot load from mock fixtures.");
  }
}

function ageHours(submittedAt?: string) {
  if (!submittedAt) return 0;
  const submittedMs = new Date(submittedAt).getTime();
  if (Number.isNaN(submittedMs)) return 0;
  return Math.max(0, Math.floor((Date.now() - submittedMs) / 3_600_000));
}

type RawApplication = Partial<Application> & {
  applicant_name?: string;
  submission_ts?: string;
  uploadedAt?: string;
  flag_count?: number;
  license_number?: string;
  originalFilename?: string;
  original_filename?: string;
  program_year?: string;
  grad_year?: string;
  graduation_year?: string;
  page_count?: number;
  document_count?: number;
  case_ref?: string;
};

interface RawSourceLocation {
  page_number?: number;
  page?: number;
  text_spans?: string[];
  spans?: string[];
}

type RawFlag = Omit<Partial<Flag>, "sourceLocation"> & {
  rule_code?: string;
  rule_name?: string;
  sourceLocation?: RawSourceLocation;
  source_location?: RawSourceLocation;
  safe_practice?: string;
};

type RawDetail = {
  application?: RawApplication;
  applicationId?: string;
  metadata?: RawApplication;
  extraction?: unknown;
  transcriptUrl?: string | null;
  transcriptPreviewStatus?: string;
  transcriptS3Key?: string | null;
  flags?: RawFlag[];
};

type RawAuditEvent = Partial<AuditEvent> & {
  timestamp?: string;
  reviewer?: string;
  action?: string;
  ruleCode?: string;
  notes?: string;
};

function stringValue(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function normalizeSeverity(value: unknown): Application["highestSeverity"] {
  if (typeof value !== "string") return null;
  switch (value.trim().toLowerCase()) {
    case "high":
      return "High";
    case "medium":
      return "Medium";
    case "low":
      return "Low";
    default:
      return null;
  }
}

function normalizeApplication(raw: RawApplication): Application {
  const submittedAt = raw.submittedAt ?? raw.submission_ts ?? raw.uploadedAt ?? "";
  return {
    applicationId: raw.applicationId ?? "",
    applicantName: raw.applicantName ?? raw.applicant_name ?? "",
    institution: raw.institution ?? "",
    country: raw.country ?? "",
    submittedAt,
    ageHours: raw.ageHours ?? ageHours(submittedAt),
    flagCount: raw.flagCount ?? raw.flag_count ?? 0,
    highestSeverity: normalizeSeverity(raw.highestSeverity),
    status: raw.status ?? "UNKNOWN",
    caseRef: raw.caseRef ?? raw.case_ref ?? null,
    licenseNumber: raw.licenseNumber ?? raw.license_number ?? "",
    originalFilename: raw.originalFilename ?? raw.original_filename ?? "",
    programYear:
      raw.programYear ?? raw.program_year ?? raw.grad_year ?? raw.graduation_year ?? "",
    pageCount: raw.pageCount ?? raw.page_count ?? raw.document_count ?? 0,
  };
}

function normalizeSourceLocation(flag: RawFlag): Flag["sourceLocation"] {
  const loc = flag.sourceLocation ?? flag.source_location;
  if (!loc || typeof loc !== "object") {
    return { page: 1, spans: [] };
  }
  const page = Number(loc.page ?? loc.page_number ?? 1);
  const spans = loc.spans ?? loc.text_spans ?? [];
  return {
    page: Number.isFinite(page) && page > 0 ? page : 1,
    spans: Array.isArray(spans) ? spans.map(String) : [],
  };
}

function safePracticeFor(ruleCode: string) {
  if (ruleCode.startsWith("CONT")) return "SP-5";
  if (ruleCode.startsWith("PROG")) return "SP-4";
  if (ruleCode.startsWith("PHYS")) return "SP-4";
  return "SP";
}

function normalizeFlag(raw: RawFlag): Flag {
  const ruleCode = stringValue(raw.ruleCode ?? raw.rule_code, "UNKNOWN");
  return {
    ruleCode,
    ruleName: stringValue(raw.ruleName ?? raw.rule_name, ruleCode),
    severity: normalizeSeverity(raw.severity) ?? "Low",
    rationale: stringValue(raw.rationale, "No rationale provided."),
    sourceLocation: normalizeSourceLocation(raw),
    status: stringValue(raw.status, "PENDING"),
    safePractice: stringValue(raw.safePractice ?? raw.safe_practice, safePracticeFor(ruleCode)),
  };
}

function normalizeExtractionRows(value: unknown): ExtractionData["physical"] {
  if (!Array.isArray(value)) return [];
  return value.map((row) => {
    if (!row || typeof row !== "object") {
      return { field: "unknown", value: String(row ?? ""), confidence: "low" as const };
    }
    const data = row as Record<string, unknown>;
    const confidence =
      typeof data.confidence === "string" && ["high", "medium", "low"].includes(data.confidence.toLowerCase())
        ? (data.confidence.toLowerCase() as "high" | "medium" | "low")
        : "low";
    return {
      field: stringValue(data.field, "unknown"),
      value: stringValue(data.value, ""),
      confidence,
      expected: typeof data.expected === "string" ? data.expected : undefined,
    };
  });
}

function normalizeExtraction(raw: unknown): ExtractionData {
  if (
    raw &&
    typeof raw === "object" &&
    "physical" in raw &&
    "content" in raw &&
    "program" in raw
  ) {
    const data = raw as Record<string, unknown>;
    return {
      physical: normalizeExtractionRows(data.physical),
      content: normalizeExtractionRows(data.content),
      program: normalizeExtractionRows(data.program),
    };
  }
  return { physical: [], content: [], program: [] };
}

function normalizeAuditEvent(raw: RawAuditEvent): AuditEvent {
  const event = raw.event ?? raw.action ?? "AUDIT_EVENT";
  const detail =
    raw.detail ??
    [raw.ruleCode, raw.notes].filter(Boolean).join(" · ") ??
    "";
  return {
    ts: raw.ts ?? raw.timestamp ?? "",
    actor: raw.actor ?? raw.reviewer ?? "system",
    event,
    detail,
  };
}

const DEFAULT_APPLICATION_STATUSES = [
  "PROCESSING",
  "READY_FOR_REVIEW",
  "FAILED",
  "INTAKE_COMPLETE",
];

export async function listApplications(options?: {
  statuses?: string[];
  limit?: number;
}): Promise<Application[]> {
  const statuses = options?.statuses ?? DEFAULT_APPLICATION_STATUSES;
  const params = new URLSearchParams();
  if (statuses.length > 0) params.set("status", statuses.join(","));
  if (options?.limit) params.set("limit", String(options.limit));
  const query = params.toString();
  const data = await fetchJson<{ items: RawApplication[] }>(
    `/applications${query ? `?${query}` : ""}`
  );
  return data.items.map(normalizeApplication);
}

export async function getApplication(id: string): Promise<{
  application: Application;
  flags: Flag[];
  extraction: ExtractionData;
  transcriptUrl: string | null;
  transcriptPreviewStatus: string;
  transcriptS3Key: string | null;
}> {
  const data = await fetchJson<RawDetail>(`/applications/${id}`);
  const metadata = data.application ?? data.metadata ?? { applicationId: data.applicationId };
  return {
    application: normalizeApplication({
      ...metadata,
      applicationId: metadata.applicationId ?? data.applicationId,
    }),
    flags: (data.flags ?? []).map(normalizeFlag),
    extraction: normalizeExtraction(data.extraction),
    transcriptUrl: data.transcriptUrl ?? null,
    transcriptPreviewStatus: data.transcriptPreviewStatus ?? "LEGACY_API_RESPONSE",
    transcriptS3Key: data.transcriptS3Key ?? null,
  };
}

export async function getAuditTrail(id: string): Promise<AuditEvent[]> {
  const data = await fetchJson<{ items: RawAuditEvent[] }>(
    `/applications/${id}/audit`
  );
  return data.items.map(normalizeAuditEvent);
}

export async function submitDecision(
  id: string,
  payload: {
    flagDecisions: { ruleCode: string; decision: string; notes: string }[];
    overallDecision: string;
  }
): Promise<void> {
  requireApiBase();
  const headers = await authHeaders();
  const res = await fetch(`${API_BASE}/applications/${id}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`API ${res.status}: decision submit failed`);
}

export async function getPageImage(id: string, page: number): Promise<{ url: string }> {
  return fetchJson(`/applications/${id}/pages/${page}`);
}

export async function uploadTranscript(file: File): Promise<{ s3Key: string }> {
  return uploadTranscriptWithDetails(file, {});
}

export async function uploadTranscriptWithDetails(
  file: File,
  details: {
    applicationId?: string;
    applicantName?: string;
    institution?: string;
    country?: string;
  }
): Promise<{ s3Key: string }> {
  requireApiBase();
  const headers = await authHeaders();
  const res = await fetch(`${API_BASE}/uploads`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify({
      filename: file.name,
      contentType: "application/pdf",
      size: file.size,
      applicationDetails: details,
    }),
  });
  if (!res.ok) throw new Error(`API ${res.status}: upload URL request failed`);

  const data = (await res.json()) as {
    uploadUrl: string;
    s3Key: string;
    metadataHeaders?: Record<string, string>;
  };
  const uploadRes = await fetch(data.uploadUrl, {
    method: "PUT",
    headers: {
      "Content-Type": "application/pdf",
      ...(data.metadataHeaders ?? {}),
    },
    body: file,
  });
  if (!uploadRes.ok) {
    throw new Error(`S3 ${uploadRes.status}: transcript upload failed`);
  }
  return { s3Key: data.s3Key };
}
