// Uses mock data until VITE_API_BASE points at the deployed API.

import type { Application, Flag, ExtractionData, AuditEvent } from "./types";
import {
  MOCK_APPLICATIONS,
  MOCK_FLAGS_BY_APP,
  CASE_A_EXTRACTION,
  MOCK_AUDIT_BY_APP,
} from "./mock-data";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

// Mock-backed API surface for local demos.

export async function listApplications(): Promise<Application[]> {
  if (!API_BASE) return MOCK_APPLICATIONS;
  const data = await fetchJson<{ items: Application[] }>("/applications");
  return data.items;
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
  return fetchJson(`/applications/${id}`);
}

export async function getAuditTrail(id: string): Promise<AuditEvent[]> {
  if (!API_BASE) return MOCK_AUDIT_BY_APP[id] ?? [];
  const data = await fetchJson<{ items: AuditEvent[] }>(
    `/applications/${id}/audit`
  );
  return data.items;
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
  await fetch(`${API_BASE}/applications/${id}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
