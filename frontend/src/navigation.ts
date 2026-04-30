import type { Application } from "./types";

export type NavigationSource = "dashboard" | "queue" | "audit";

export const APP_ROUTES = {
  dashboard: "/dashboard",
  queue: "/queue",
  upload: "/upload",
  audit: "/audit",
  settings: "/settings",
} as const;

export type AppRouteId = keyof typeof APP_ROUTES;

export interface BackTarget {
  pathname: string;
  label: string;
}

export interface DetailBackState {
  from?: BackTarget;
}

const BACK_TARGETS: Record<NavigationSource, BackTarget> = {
  dashboard: { pathname: APP_ROUTES.dashboard, label: "Dashboard" },
  queue: { pathname: APP_ROUTES.queue, label: "Review Queue" },
  audit: { pathname: APP_ROUTES.audit, label: "Audit Log" },
};

function applicationId(value: Application | string) {
  return typeof value === "string" ? value : value.applicationId;
}

export function applicationReviewPath(app: Application | string) {
  return `/review/${applicationId(app)}`;
}

export function applicationAuditPath(app: Application | string) {
  return `/audit/${applicationId(app)}`;
}

export function applicationReviewedPath(app: Application | string) {
  return `/reviewed/${applicationId(app)}`;
}

const REVIEW_OUTCOME_STATUSES = new Set([
  "REVIEWED",
  "READY_FOR_LICENSING_REVIEW",
  "RETURN_TO_APPLICANT",
  "DEFERRED",
  "DENIED",
  "APPROVED",
  "CLOSED",
  "COMPLETED",
]);

export function hasApplicationSummary(app: Application) {
  return Boolean(app.applicantName.trim() || app.institution.trim());
}

export function isApplicationReviewable(app: Application) {
  return app.status === "READY_FOR_REVIEW" && hasApplicationSummary(app);
}

export function applicationDetailPath(app: Application, source: NavigationSource) {
  if (isApplicationReviewable(app)) return applicationReviewPath(app);
  if (REVIEW_OUTCOME_STATUSES.has(app.status)) return applicationReviewedPath(app);
  if (source === "dashboard" && app.status === "FAILED") {
    return applicationAuditPath(app);
  }
  return null;
}

export function sourceFromSection(id: string): NavigationSource {
  if (id === "queue" || id === "audit") return id;
  return "dashboard";
}

export function applicationBackTarget(source: NavigationSource): BackTarget {
  return BACK_TARGETS[source];
}

export function appSectionPath(id: string) {
  return APP_ROUTES[id as AppRouteId] ?? APP_ROUTES.dashboard;
}

export function detailBackStateFor(source: NavigationSource): { state: DetailBackState } {
  const target = applicationBackTarget(source);
  return {
    state: {
      from: target,
    },
  };
}
