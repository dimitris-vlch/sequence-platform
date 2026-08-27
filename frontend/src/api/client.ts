// Types for the backend API. The field names mirror the FastAPI
// endpoint schemas; keep them in sync when the backend changes.

export interface HealthResponse {
  ok: boolean;
  service: string;
  version: string;
  time: string;
  databases: string[];
}

export const API_BASE_URL = "/api";

export function httpErrorDetail(status: number, body: string): string {
  if (body === "") {
    return `HTTP ${status}`;
  }
  try {
    const parsed = JSON.parse(body) as { detail?: string };
    if (parsed.detail !== undefined) {
      return parsed.detail;
    }
  } catch {
    // Not JSON - fall back to the raw body.
  }
  return body.length > 120 ? `${body.slice(0, 120)}…` : body;
}

export async function fetchWithHttpError(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(httpErrorDetail(response.status, body));
  }
  return response;
}

/** Query the backend health endpoint. */
export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetchWithHttpError(`${API_BASE_URL}/health`);
  return (await response.json()) as HealthResponse;
}
