import type { components } from "@/lib/api/schema";

const DEFAULT_API_BASE = "http://localhost:8000";

export type Incident = components["schemas"]["IncidentResponse"];
export type IncidentList = components["schemas"]["IncidentListResponse"];
export type SimulatedIncidentCreate = components["schemas"]["SimulatedIncidentCreate"];
export type FunnelResult = components["schemas"]["FunnelResult"];
export type DiagnosisRun = components["schemas"]["DiagnosisRunResponse"];
export type DiagnosisReport = components["schemas"]["ReportResponse"];
export type DiagnosisTrace = components["schemas"]["DiagnosisTraceResponse"];
export type DiagnosisEvent = components["schemas"]["DiagnosisRunEventSchema"];
export type DiagnosisRunTrigger = components["schemas"]["DiagnosisRunTriggerResponse"];
export type DiagnosisRunRetry = components["schemas"]["DiagnosisRunRetryResponse"];
export type Evidence = components["schemas"]["EvidenceResponse"];
export type EvaluationRun = components["schemas"]["EvaluationRunResponse"];
export type EvaluationList = components["schemas"]["EvaluationRunListResponse"];
export type EvaluationCreate = components["schemas"]["EvaluationRunCreate"];
export type EvaluationTrigger = components["schemas"]["EvaluationRunTriggerResponse"];

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly payload: unknown;

  constructor(status: number, detail: string, payload: unknown = null) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.payload = payload;
  }
}

export function apiBaseUrl(): string {
  const configured =
    typeof window === "undefined"
      ? process.env.PAYTRACE_API_BASE
      : process.env.NEXT_PUBLIC_PAYTRACE_API_BASE;
  return (configured || DEFAULT_API_BASE).replace(/\/$/, "");
}

export function apiUrl(path: string): string {
  return `${apiBaseUrl()}${path}`;
}

function errorDetail(payload: unknown, fallback: string): string {
  if (typeof payload === "object" && payload !== null && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === "string") return message;
    }
  }
  return fallback;
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...init,
      headers,
      cache: "no-store",
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Network request failed";
    throw new ApiError(0, message);
  }

  const raw = await response.text();
  let payload: unknown = null;
  if (raw) {
    try {
      payload = JSON.parse(raw) as unknown;
    } catch {
      payload = raw;
    }
  }
  if (!response.ok) {
    throw new ApiError(
      response.status,
      errorDetail(payload, `Request failed with HTTP ${response.status}`),
      payload,
    );
  }
  return payload as T;
}

export function jsonBody(value: unknown): BodyInit {
  return JSON.stringify(value);
}
