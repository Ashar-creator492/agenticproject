export type User = {
  id: string;
  email: string;
  display_name: string;
  role: "importer_investigator" | "retailer_safety_manager" | "manufacturer_reviewer";
  organization_id: string;
};

export type Organization = { id: string; code: string; name: string; type: "retailer" | "manufacturer" };
export type ProductRecord = { id: string; sku: string; name: string; manufacturer: { code: string; name: string } };
export type BatchRecord = { id: string; sku: string; product_name: string; batch_number: string; quantity_received: number; expiry_date: string | null };
export type ShipmentRecord = { id: string; shipment_reference: string; sku: string; batch_number: string; retailer_code: string; retailer_name: string; quantity: number; shipped_at: string };

export type CaseSummary = {
  id: string;
  public_id: string;
  source: string;
  reporter_name: string | null;
  product_name: string;
  batch_number: string | null;
  status: string;
  safety_verdict: string;
  retailer_id: string | null;
  created_at: string;
  updated_at: string;
};

export type AgentRun = {
  id: string;
  agent_type: "triage" | "traceability" | "escalation";
  status: string;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  completed_at: string | null;
};

export type Proposal = {
  review_block_reason: string | null;
  id: string;
  type: string;
  payload: Record<string, unknown>;
  status: string;
  version: number;
  created_at: string;
};

export type Inspection = {
  id: string;
  case_id?: string;
  retailer_id?: string;
  retailer_name?: string;
  status: string;
  finding: string | null;
  notes: string | null;
  created_at: string;
  completed_at: string | null;
};

export type TimelineEvent = {
  id: string;
  event_type: string;
  actor_user_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
};

export type CaseDetail = {
  workflow: Record<AgentRun["agent_type"], { can_run: boolean; blocked_reason: string | null; latest_proposal_id: string | null }>;
  manufacturer_response: string | null;
  case: CaseSummary;
  description: string;
  proposals: Proposal[];
  inspections: Inspection[];
  timeline: TimelineEvent[];
  agent_runs: AgentRun[];
  evidence: { id: string; filename: string; content_type: string; url: string }[];
  retailer_review: { decision: string; notes: string } | null;
  demo_verification: DemoBarcodeMatch | null;
};

export type DemoBarcodeMatch = {
  simulated: boolean;
  barcode: string;
  sku: string;
  product_name: string;
  product_id: string;
  batch_number: string;
  batch_id: string;
};

export type Escalation = {
  id: string;
  case_id: string;
  packet: Record<string, unknown>;
  status: string;
  response: string | null;
  created_at: string;
};
