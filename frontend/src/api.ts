// Uses mock data until VITE_API_BASE points at the deployed API.

import type { Application, Flag, ExtractionData, AuditEvent } from "./types";
import {
  MOCK_APPLICATIONS,
  MOCK_FLAGS_BY_APP,
  CASE_A_EXTRACTION,
  MOCK_AUDIT_BY_APP,
} from "./mock-data";
import { getIdToken } from "./auth";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function fetchJson<T>(path: string): Promise<T> {
  const headers = await authHeaders();
  const res = await fetch(`${API_BASE}${path}`, { headers });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

async function authHeaders() {
  const token = await getIdToken();
  return token ? { Authorization: `Bearer ${token}` } : undefined;
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
  flags?: RawFlag[];
};

type RawAuditEvent = Partial<AuditEvent> & {
  timestamp?: string;
  reviewer?: string;
  action?: string;
  ruleCode?: string;
  notes?: string;
};

function normalizeApplication(raw: RawApplication): Application {
  const submittedAt = raw.submittedAt ?? raw.submission_ts ?? raw.uploadedAt ?? "";
  return {
    applicationId: raw.applicationId ?? "",
    applicantName: raw.applicantName ?? raw.applicant_name ?? "Unknown applicant",
    institution: raw.institution ?? "Unknown institution",
    country: raw.country ?? "—",
    submittedAt,
    ageHours: raw.ageHours ?? ageHours(submittedAt),
    flagCount: raw.flagCount ?? raw.flag_count ?? 0,
    highestSeverity: raw.highestSeverity ?? null,
    status: raw.status ?? "UNKNOWN",
    caseRef: raw.caseRef ?? raw.case_ref ?? null,
    licenseNumber: raw.licenseNumber ?? raw.license_number ?? "—",
    programYear:
      raw.programYear ?? raw.program_year ?? raw.grad_year ?? raw.graduation_year ?? "—",
    pageCount: raw.pageCount ?? raw.page_count ?? raw.document_count ?? 0,
  };
}

function normalizeSourceLocation(flag: RawFlag): Flag["sourceLocation"] {
  const loc = flag.sourceLocation ?? flag.source_location;
  return {
    page: loc?.page ?? loc?.page_number ?? 1,
    spans: loc?.spans ?? loc?.text_spans ?? [],
  };
}

function safePracticeFor(ruleCode: string) {
  if (ruleCode.startsWith("CONT")) return "SP-5";
  if (ruleCode.startsWith("PROG")) return "SP-4";
  if (ruleCode.startsWith("PHYS")) return "SP-4";
  return "SP";
}

function normalizeFlag(raw: RawFlag): Flag {
  const ruleCode = raw.ruleCode ?? raw.rule_code ?? "UNKNOWN";
  return {
    ruleCode,
    ruleName: raw.ruleName ?? raw.rule_name ?? ruleCode,
    severity: raw.severity ?? "Low",
    rationale: raw.rationale ?? "No rationale provided.",
    sourceLocation: normalizeSourceLocation(raw),
    status: raw.status ?? "PENDING",
    safePractice: raw.safePractice ?? raw.safe_practice ?? safePracticeFor(ruleCode),
  };
}

function normalizeExtraction(raw: unknown): ExtractionData {
  if (
    raw &&
    typeof raw === "object" &&
    "physical" in raw &&
    "content" in raw &&
    "program" in raw
  ) {
    return raw as ExtractionData;
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

// Mock-backed API surface for local demos.

export async function listApplications(): Promise<Application[]> {
  if (!API_BASE) return MOCK_APPLICATIONS;
  const data = await fetchJson<{ items: RawApplication[] }>("/applications");
  return data.items.map(normalizeApplication);
}

export async function getApplication(id: string): Promise<{
  application: Application;
  flags: Flag[];
  extraction: ExtractionData;
}> {
  if (!API_BASE) {
    const app = MOCK_APPLICATIONS.find((a) => a.applicationId === id);
    if (!app) throw new Error(`Application ${id} not found`);
    return { application: app, flags: MOCK_FLAGS_BY_APP[id] ?? [], extraction: CASE_A_EXTRACTION };
  }
  const data = await fetchJson<RawDetail>(`/applications/${id}`);
  const metadata = data.application ?? data.metadata ?? { applicationId: data.applicationId };
  return {
    application: normalizeApplication({
      ...metadata,
      applicationId: metadata.applicationId ?? data.applicationId,
    }),
    flags: (data.flags ?? []).map(normalizeFlag),
    extraction: normalizeExtraction(data.extraction),
  };
}

export async function getAuditTrail(id: string): Promise<AuditEvent[]> {
  if (!API_BASE) return MOCK_AUDIT_BY_APP[id] ?? [];
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
  if (!API_BASE) {
    // Local mock only; the real API call is below.
    console.log("Decision submitted (mock):", id, payload);
    return;
  }
  const headers = await authHeaders();
  const res = await fetch(`${API_BASE}/applications/${id}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`API ${res.status}: decision submit failed`);
}
