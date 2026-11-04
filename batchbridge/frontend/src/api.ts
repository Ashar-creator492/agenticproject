import type { BatchRecord, CaseDetail, CaseSummary, DemoBarcodeMatch, Escalation, Inspection, Organization, ProductRecord, ShipmentRecord, User } from "./types";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...options, headers, credentials: "include" });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  me: () => request<User>("/api/v1/auth/me"),
  login: (email: string, password: string) =>
    request<User>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),
  report: (payload: Record<string, string>) =>
    request<{ case_id: string; tracking_token: string; tracking_url: string; status: string }>(
      "/api/v1/reports",
      { method: "POST", body: JSON.stringify(payload) },
    ),
  photoReport: (payload: FormData) =>
    request<{ case_id: string; tracking_token: string; tracking_url: string; status: string }>(
      "/api/v1/reports/photo", { method: "POST", body: payload },
    ),
  retailers: () => request<{ code: string; name: string }[]>("/api/v1/catalog/retailers"),
  organizations: () => request<Organization[]>("/api/v1/organizations"),
  products: () => request<ProductRecord[]>("/api/v1/catalog/products"),
  officerReport: (payload: { product_name: string; batch_number: string; description: string; purchase_date?: string }) =>
    request<CaseSummary>("/api/v1/cases/officer-report", { method: "POST", body: JSON.stringify(payload) }),
  createOrganization: (payload: { code: string; name: string; type: "retailer" | "manufacturer"; staff_name: string; staff_email: string; staff_password: string }) =>
    request<Organization>("/api/v1/organizations", { method: "POST", body: JSON.stringify(payload) }),
  batches: () => request<BatchRecord[]>("/api/v1/catalog/batches"),
  shipments: () => request<ShipmentRecord[]>("/api/v1/catalog/shipments"),
  lookupBarcode: (caseId: string, barcode: string) =>
    request<DemoBarcodeMatch>(`/api/v1/cases/${caseId}/demo-barcode`, {
      method: "POST", body: JSON.stringify({ barcode }),
    }),
  track: (token: string) =>
    request<{
      case_id: string;
      product_name: string;
      status: string;
      safety_verdict: string;
      updated_at: string;
    }>(`/api/v1/tracking/${encodeURIComponent(token)}`),
  addInformation: (caseId: string, notes: string, productName?: string, batchNumber?: string) =>
    request(`/api/v1/cases/${caseId}/information`, { method: "POST", body: JSON.stringify({ notes, product_name: productName || undefined, batch_number: batchNumber || undefined }) }),
  closeCase: (caseId: string, notes: string, safetyVerdict: string) =>
    request(`/api/v1/cases/${caseId}/status`, { method: "PATCH", body: JSON.stringify({ status: "closed", notes, safety_verdict: safetyVerdict }) }),
  cases: () => request<CaseSummary[]>("/api/v1/cases"),
  caseDetail: (caseId: string) => request<CaseDetail>(`/api/v1/cases/${caseId}`),
  startAgent: (caseId: string, agent: "triage" | "traceability" | "escalation") => {
    const suffix =
      agent === "triage"
        ? "triage"
        : agent === "traceability"
          ? "analysis"
          : "escalation-analysis";
    return request<{ run_id: string; status: string; agent_type: string }>(
      `/api/v1/cases/${caseId}/${suffix}`,
      { method: "POST" },
    );
  },
  reviewCase: (caseId: string, decision: string, notes: string, demoBarcode?: string) =>
    request(`/api/v1/cases/${caseId}/retailer-review`, {
      method: "POST",
      body: JSON.stringify({ decision, notes, demo_barcode: demoBarcode }),
    }),
  approve: (caseId: string, proposalId: string, decision: string, notes: string) =>
    request(`/api/v1/cases/${caseId}/approvals`, {
      method: "POST",
      body: JSON.stringify({ proposal_id: proposalId, decision, notes }),
    }),
  inspections: () => request<Inspection[]>("/api/v1/inspections"),
  submitFinding: (inspectionId: string, finding: string, notes: string) =>
    request(`/api/v1/inspections/${inspectionId}/finding`, {
      method: "POST",
      body: JSON.stringify({ finding, notes }),
    }),
  importCsv: (kind: "batches" | "shipments", file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<{ inserted: number; skipped: number; errors: Record<string, unknown>[] }>(
      `/api/v1/imports/${kind}`,
      { method: "POST", body },
    );
  },
  escalations: () => request<Escalation[]>("/api/v1/escalations"),
  manufacturerReportUrl: (escalationId: string) =>
    `/api/v1/escalations/${encodeURIComponent(escalationId)}/report.csv`,
  respond: (escalationId: string, response: string) =>
    request(`/api/v1/escalations/${escalationId}/response`, {
      method: "POST",
      body: JSON.stringify({ response }),
    }),
};
