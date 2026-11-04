import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { api } from "./api";
import { Brand } from "./Brand";
import { createDemoPhoto } from "./demoPhoto";
import { HowItWorks } from "./HowItWorks";
import type {
  AgentRun,
  BatchRecord,
  CaseDetail,
  CaseSummary,
  DemoBarcodeMatch,
  Escalation,
  Inspection,
  Organization,
  ProductRecord,
  Proposal,
  ShipmentRecord,
  User,
} from "./types";

const stageMeta = {
  triage: { number: "01", title: "Review report", action: "Review report details", description: "Checks the report and identifies missing information" },
  traceability: {
    number: "02",
    title: "Trace affected batch",
    action: "Trace affected batch",
    description: "Matches the verified product and lot to shipment destinations",
  },
  escalation: {
    number: "03",
    title: "Prepare manufacturer review",
    action: "Prepare manufacturer review",
    description: "Combines approved evidence for manufacturer response",
  },
} as const;

function proposalTitle(type: string) {
  if (type === "triage_recommendation") return "Report review recommendation";
  if (type === "retailer_check_plan") return "Retailer inspection plan";
  if (type === "manufacturer_escalation_packet") return "Manufacturer evidence package";
  return label(type);
}

function stakeholderText(value: string) {
  const terms: Record<string, string> = {
    triage: "report review",
    traceability: "batch tracing",
    escalation: "manufacturer review",
    agent: "evidence check",
    proposal: "recommendation",
  };
  return value.replace(/\b(triage|traceability|escalation|agent|proposal)\b/gi, (term) => {
    const replacement = terms[term.toLowerCase()];
    return term[0] === term[0].toUpperCase()
      ? replacement[0].toUpperCase() + replacement.slice(1)
      : replacement;
  });
}

function label(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatDate(value: string | null) {
  if (!value) return "Pending";
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function asArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
}

function asRecord(value: unknown): Record<string, unknown> {
  return value != null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function displayValue(value: unknown, fallback = "Not provided") {
  return value == null || value === "" ? fallback : String(value);
}

function InvestigationIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4h6M9 7h6M8 3h8a2 2 0 0 1 2 2v15H6V5a2 2 0 0 1 2-2Z" /><path d="m9 13 2 2 4-4" /></svg>;
}

function SettingsIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.55V21h-4v-.08A1.7 1.7 0 0 0 8.97 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.52-1.03H3v-4h.08A1.7 1.7 0 0 0 4.6 8.94a1.7 1.7 0 0 0-.34-1.88L4.2 7l2.83-2.83.06.06a1.7 1.7 0 0 0 1.88.34A1.7 1.7 0 0 0 10 3.05V3h4v.05a1.7 1.7 0 0 0 1.03 1.52 1.7 1.7 0 0 0 1.88-.34l.06-.06L19.8 7l-.06.06a1.7 1.7 0 0 0-.34 1.88A1.7 1.7 0 0 0 20.92 10H21v4h-.08A1.7 1.7 0 0 0 19.4 15Z" /></svg>;
}

function ManufacturerReport({ packet, downloadUrl }: { packet: Record<string, unknown>; downloadUrl?: string }) {
  const product = asRecord(packet.product);
  const manufacturer = asRecord(product.manufacturer);
  const batch = asRecord(packet.batch);
  const summary = asRecord(packet.distribution_summary);
  const distribution = asArray(packet.distribution);
  const findings = asArray(packet.findings);
  const evidence = asArray(packet.evidence);
  const actions = Array.isArray(packet.requested_actions)
    ? packet.requested_actions
    : Array.isArray(packet.manufacturer_questions)
      ? packet.manufacturer_questions
      : [];
  return (
    <div className="manufacturer-report">
      <div className="manufacturer-report-head">
        <div><span className="eyebrow">Manufacturer report</span><h3>{displayValue(product.name, "Product investigation")}</h3><p>Case {displayValue(packet.case_public_id)} · Lot {displayValue(batch.batch_number)}</p></div>
        {downloadUrl ? <a className="button button-secondary" href={downloadUrl} download>Download CSV</a> : <span className="csv-note">CSV created when this report is sent</span>}
      </div>
      <div className="report-facts">
        <span><small>Manufacturer</small><strong>{displayValue(manufacturer.name)}</strong></span>
        <span><small>Product code</small><strong>{displayValue(product.sku)}</strong></span>
        <span><small>Received</small><strong>{Number(batch.quantity_received ?? 0).toLocaleString()} units</strong></span>
        <span><small>Shipped</small><strong>{Number(summary.quantity_shipped ?? batch.quantity_shipped ?? 0).toLocaleString()} units</strong></span>
        <span><small>Retained</small><strong>{Number(summary.quantity_retained ?? batch.quantity_retained ?? 0).toLocaleString()} units</strong></span>
      </div>
      {distribution.length > 0 && <div className="report-section"><h4>Where this lot was shipped</h4><div className="report-table-wrap"><table className="report-table"><thead><tr><th>Supermarket</th><th>Shipment</th><th>Quantity</th><th>Shipped</th></tr></thead><tbody>{distribution.map((item) => <tr key={displayValue(item.shipment_id)}><td>{displayValue(item.retailer_name)}</td><td>{displayValue(item.shipment_reference)}</td><td>{Number(item.quantity ?? 0).toLocaleString()}</td><td>{formatDate(item.shipped_at ? String(item.shipped_at) : null)}</td></tr>)}</tbody></table></div></div>}
      {findings.length > 0 && <div className="report-section"><h4>Human inspection findings</h4><div className="report-table-wrap"><table className="report-table"><thead><tr><th>Supermarket</th><th>Finding</th><th>Inspector notes</th><th>Completed</th></tr></thead><tbody>{findings.map((item) => <tr key={displayValue(item.inspection_id)}><td>{displayValue(item.retailer_name)}</td><td><Pill value={displayValue(item.finding, "pending")} /></td><td>{displayValue(item.notes)}</td><td>{formatDate(item.completed_at ? String(item.completed_at) : null)}</td></tr>)}</tbody></table></div></div>}
      {actions.length > 0 && <div className="report-section"><h4>Requested manufacturer actions</h4><ol className="report-actions">{actions.map((item, index) => <li key={index}>{String(item)}</li>)}</ol></div>}
      {evidence.length > 0 && <div className="report-section"><h4>Supporting evidence</h4><div className="report-files">{evidence.map((item) => <a key={displayValue(item.id)} href={`/api/v1/evidence/${encodeURIComponent(displayValue(item.id))}`} target="_blank" rel="noreferrer">{displayValue(item.filename)} ↗</a>)}</div></div>}
      {packet.importer_notes != null && <div className="report-section"><h4>Importer notes</h4><p>{String(packet.importer_notes)}</p></div>}
      <details className="technical-details"><summary>Technical details</summary><pre>{JSON.stringify(packet, null, 2)}</pre></details>
    </div>
  );
}

function Pill({ value }: { value: string }) {
  const tone =
    value.includes("approved") || value.includes("completed") || value.includes("responded")
      ? "success"
      : value.includes("failed") || value.includes("rejected")
        ? "danger"
        : value.includes("waiting") || value.includes("pending") || value.includes("human")
          ? "warning"
          : "neutral";
  return <span className={`pill pill-${tone}`}>{label(value)}</span>;
}

function PublicNavigation({ onLogin }: { onLogin: () => void }) {
  return (
      <nav className="public-nav">
        <a href="/" aria-label="Escalera home"><Brand /></a>
        <div className="public-links" aria-label="Page navigation">
          <a href="/how-it-works">How it works</a>
          <a href="/safety-controls">Safety controls</a>
        </div>
        <button className="button button-nav" onClick={onLogin}>Staff portal <span>↗</span></button>
      </nav>
  );
}

function PublicInfoPage({ page, onLogin }: { page: "how-it-works" | "safety-controls"; onLogin: () => void }) {
  return (
    <main className="public-shell">
      <PublicNavigation onLogin={onLogin} />
      <div className="public-nav"><a className="text-link" href="/">← Back to main page</a></div>
      {page === "how-it-works" ? (
      <HowItWorks onLogin={onLogin} />
      ) : (
      <section className="control-section" id="safety-controls">
        <div className="control-visual" aria-hidden="true">
          <div className="control-orbit orbit-one" /><div className="control-orbit orbit-two" />
          <div className="control-core"><span>BB</span><small>human<br />control</small></div>
          <span className="control-chip chip-one">Verified batch</span>
          <span className="control-chip chip-two">Approved action</span>
          <span className="control-chip chip-three">Audit event</span>
        </div>
        <div className="control-copy">
          <h2>Evidence organized.<br />People decide.</h2>
          <p>Escalera prepares evidence and suggested next steps. Authorized people approve every operational decision.</p>
          <div className="control-list">
            <span><i>✓</i> Product and lot matched together</span>
            <span><i>✓</i> Customer contact data stays protected</span>
            <span><i>✓</i> Meaningful actions enter audit trail</span>
          </div>
        </div>
      </section>
      )}
    </main>
  );
}

function PublicReport({ onLogin }: { onLogin: () => void }) {
  const [form, setForm] = useState({
    reporter_name: "",
    reporter_email: "",
    retailer_code: "",
    purchase_date: "",
    description: "",
  });
  const [created, setCreated] = useState<Awaited<ReturnType<typeof api.report>> | null>(null);
  const [trackingToken, setTrackingToken] = useState("");
  const [tracked, setTracked] = useState<Awaited<ReturnType<typeof api.track>> | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [retailers, setRetailers] = useState<{ code: string; name: string }[]>([]);
  const [photos, setPhotos] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);

  useEffect(() => {
    void api.retailers().then(setRetailers).catch(() => setError("Unable to load supermarkets. Please refresh."));
  }, []);
  useEffect(() => {
    const urls = photos.map((file) => URL.createObjectURL(file));
    setPreviews(urls);
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, [photos]);

  function selectPhotos(files: File[]) {
    setError("");
    if (files.length > 3 || files.some((file) => !["image/jpeg", "image/png"].includes(file.type) || file.size > 5 * 1024 * 1024)) {
      setError("Choose up to three JPEG or PNG photos, each no larger than 5 MB.");
      return;
    }
    setPhotos(files);
  }

  async function useDemoPhoto() {
    setBusy(true); setError("");
    try {
      setPhotos([await createDemoPhoto()]);
      setForm((current) => ({ ...current, retailer_code: "RETAILER-A", description: current.description || "The sealed chocolate had an unusual smell and visible discoloration." }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to create demo photo"); }
    finally { setBusy(false); }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (!photos.length) throw new Error("Add a product photo or use the demo photo below.");
      const payload = new FormData();
      for (const [key, value] of Object.entries(form)) if (value) payload.append(key, value);
      for (const photo of photos) payload.append("files", photo);
      const result = await api.photoReport(payload);
      setCreated(result);
      setTrackingToken(result.tracking_token);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to submit report");
    } finally {
      setBusy(false);
    }
  }

  async function track(event: FormEvent) {
    event.preventDefault();
    setError("");
    setTracked(null);
    try {
      setTracked(await api.track(trackingToken.trim()));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to find report");
    }
  }

  return (
    <main className="public-shell">
      <PublicNavigation onLogin={onLogin} />
      <section className="hero-grid">
        <div className="hero-copy">
          <h1>From first report to <em>verified action.</em></h1>
          <p>
            Report a product concern in minutes. Escalera connects verified evidence,
            exact batch records, and accountable human decisions in one secure investigation.
          </p>
          <div className="hero-actions">
            <a className="button button-primary" href="#report-form">Report a concern</a>
            <a className="text-link" href="/how-it-works">See how it works <span>↓</span></a>
          </div>
          <form className="tracking-box" onSubmit={track}>
            <div><span className="tracking-icon">⌁</span><span><strong>Track an existing report</strong><small>Use your private tracking token.</small></span></div>
            <div className="tracking-controls"><input aria-label="Private tracking token" required value={trackingToken} onChange={(event) => setTrackingToken(event.target.value)} placeholder="Enter tracking token" /><button className="button button-secondary">Track report</button></div>
            {tracked && <div className="tracking-result"><div><strong>{tracked.case_id}</strong><span>{tracked.product_name}</span></div><Pill value={tracked.status} /><Pill value={tracked.safety_verdict} /></div>}
          </form>
        </div>
        <form className="report-card" id="report-form" onSubmit={submit}>
          <div className="form-header">
            <div>
              <h2>Tell us what happened</h2>
              <p className="muted">No product codes needed. Officer verifies product and batch.</p>
            </div>
          </div>
          <div className="form-grid two">
            <label>Name<input value={form.reporter_name} onChange={(event) => setForm({ ...form, reporter_name: event.target.value })} /></label>
            <label>Email<input type="email" value={form.reporter_email} onChange={(event) => setForm({ ...form, reporter_email: event.target.value })} /></label>
          </div>
          <label>Where did you buy it?<select required disabled={busy || Boolean(created)} value={form.retailer_code} onChange={(event) => setForm({ ...form, retailer_code: event.target.value })}>
            <option value="">Choose your supermarket</option>
            {retailers.map((retailer) => <option key={retailer.code} value={retailer.code}>{retailer.name}</option>)}
          </select></label>
          <div className="photo-upload">
            <strong>Show us the packaging and the problem</strong>
            <p className="muted small" id="photo-help">Include a clear photo of the barcode or printed code. Up to 3 JPEG/PNG photos, 5 MB each.</p>
            <input aria-label="Product photos" aria-describedby="photo-help" type="file" accept="image/jpeg,image/png" multiple disabled={busy || Boolean(created)} onChange={(event) => selectPhotos(Array.from(event.target.files ?? []))} />
            <div className="photo-preview-grid">{photos.map((photo, index) => <figure key={`${photo.name}-${index}`}><img src={previews[index]} alt={`Selected product photo ${index + 1}`} /><figcaption>{photo.name}</figcaption></figure>)}</div>
            <button type="button" className="button button-secondary" disabled={busy || Boolean(created)} onClick={() => void useDemoPhoto()}>Try with a demo photo</button>
            <span className="muted small">Fictional chocolate packaging for trying the full workflow.</span>
          </div>
          <label>Purchase date<input type="date" value={form.purchase_date} onChange={(event) => setForm({ ...form, purchase_date: event.target.value })} /></label>
          <label>What did you observe?<textarea required minLength={10} rows={4} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
          {error && <div className="alert danger">{error}</div>}
          {created && (
            <div className="alert success">
              <strong>Report {created.case_id} created.</strong>
              <span>Your supermarket officer will review the photos and verify the product.</span>
              <span>Save this private tracking token: <code>{created.tracking_token}</code></span>
              <button type="button" className="button button-secondary" onClick={() => { setCreated(null); setPhotos([]); setForm((current) => ({ ...current, description: "" })); }}>Report another issue</button>
            </div>
          )}
          <button className="button button-primary" disabled={busy || Boolean(created)}>{busy ? "Preparing report…" : created ? "Report received" : "Send to supermarket officer"}</button>
          <p className="form-footnote">Your report remains private and creates a complete audit record.</p>
        </form>
      </section>
      <footer className="public-footer">
        <Brand />
        <p>Food safety intelligence with human accountability.</p>
        <button className="button button-ghost" onClick={onLogin}>Open staff portal</button>
      </footer>
    </main>
  );
}

function Login({ onSuccess, onBack }: { onSuccess: (user: User) => void; onBack: () => void }) {
  const [email, setEmail] = useState("importer@escalera.demo");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      onSuccess(await api.login(email, password));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to sign in");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-shell">
      <button className="back-link" onClick={onBack}>← Return to report form</button>
      <form className="login-card" onSubmit={submit}>
        <Brand className="brand-large" markOnly />
        <div><h1>Continue your investigation</h1></div>
        <label>Email<input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
        <label>Password<input required type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        {error && <div className="alert danger">{error}</div>}
        <button className="button button-primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <p className="muted small">Use a seeded account and the configured DEMO_PASSWORD.</p>
      </form>
    </main>
  );
}

function AgentCard({ agent, run, gate }: { agent: keyof typeof stageMeta; run?: AgentRun; gate: CaseDetail["workflow"][AgentRun["agent_type"]] }) {
  const meta = stageMeta[agent];
  const result = run?.result;
  const assessment = result?.ai_assessment as { summary?: string; unanswered_questions?: string[] } | undefined;
  const toolCalls = asArray(result?.tool_calls);
  const confidence = typeof result?.confidence === "string" ? result.confidence : null;
  const recommendation =
    typeof result?.recommendation === "string" ? result.recommendation : null;
  return (
    <article className={`agent-card ${run?.status === "completed" ? "complete" : run || gate.can_run ? "active" : "locked"}`}>
      <div className="agent-heading">
        <span className="agent-number">{meta.number}</span>
        <div><h3>{meta.title}</h3><p>{meta.description}</p></div>
        <Pill value={run?.status ?? (gate.can_run ? "ready" : "locked")} />
      </div>
      {run ? (
        <div className="agent-body">
          {assessment?.summary && <p className="muted small">{assessment.summary}</p>}
          {assessment?.unanswered_questions && assessment.unanswered_questions.length > 0 && <div className="small"><strong>Follow-up questions</strong><ul>{assessment.unanswered_questions.map((question, index) => <li key={index}>{question}</li>)}</ul></div>}
          <div className="metric-row">
            {confidence && <span><small>Confidence</small><strong>{label(confidence)}</strong></span>}
            {recommendation && <span><small>Suggested next step</small><strong>{label(recommendation)}</strong></span>}
          </div>
          {gate.blocked_reason && !["queued", "running"].includes(run.status) && <div className="stage-guidance" role="status"><strong>Before you continue</strong><span>{stakeholderText(gate.blocked_reason)}</span></div>}
          {run.error && <div className="alert danger"><strong>This step could not finish.</strong><span>Try again. Contact system support if the problem continues.</span></div>}
          {result && <details className="technical-details"><summary>Technical details</summary>
            <div className="technical-body">
              <span>{result.execution_mode === "llm" ? `Groq · ${String(result.model)} · ${String(result.llm_turns)} model turns` : result.execution_mode === "rules" ? "Rules-based evidence check" : "Previous demonstration run"}</span>
              <span>{toolCalls.length} evidence tool call(s)</span>
              {toolCalls.length > 0 && <div className="tool-list">{toolCalls.map((call, index) => <span key={`${String(call.tool)}-${index}`}>{String(call.tool)} · {String(call.record_count ?? 0)} records</span>)}</div>}
              {run.error && <code>{run.error}</code>}
            </div>
          </details>}
        </div>
      ) : <p className="locked-copy">{gate.blocked_reason ? stakeholderText(gate.blocked_reason) : "Ready. Use the next action below to begin this step."}</p>}
    </article>
  );
}

function ProposalReview({ proposal, caseId, onDone }: { proposal: Proposal; caseId: string; onDone: () => Promise<void> }) {
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const retailers = asArray(proposal.payload.retailers);

  async function decide(decision: "approved" | "rejected") {
    setBusy(true);
    setError("");
    try {
      await api.approve(caseId, proposal.id, decision, notes);
      await onDone();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Decision failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel approval-panel">
      <div className="section-heading"><div><span className="eyebrow">Approval needed</span><h2>{proposalTitle(proposal.type)}</h2></div><Pill value={proposal.status} /></div>
      <p className="muted">Review recommendation version {proposal.version} before anything is sent or assigned.</p>
      {proposal.review_block_reason && <div className="alert">{stakeholderText(proposal.review_block_reason)}</div>}
      {proposal.payload.recommendation != null && <p><strong>Recommendation:</strong> {label(String(proposal.payload.recommendation))}</p>}
      {asArray(proposal.payload.rationale).map((reason, index) => <p key={index}>{String(reason)}</p>)}
      {retailers.length > 0 && (
        <div className="recipient-grid">
          {retailers.map((retailer) => (
            <div className="recipient" key={String(retailer.retailer_id)}>
              <strong>{String(retailer.retailer_name)}</strong>
              <span>{Number(retailer.quantity).toLocaleString()} units</span>
            </div>
          ))}
        </div>
      )}
      {proposal.type === "manufacturer_escalation_packet" && (
        <ManufacturerReport packet={asRecord(proposal.payload.manufacturer_packet)} />
      )}
      <label>Reviewer notes<textarea rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Record the reason for your decision" /></label>
      {error && <div className="alert danger">{error}</div>}
      <div className="action-row">
        <button className="button button-primary" disabled={busy || Boolean(proposal.review_block_reason)} onClick={() => void decide("approved")}>Approve and continue</button>
        <button className="button button-danger" disabled={busy || Boolean(proposal.review_block_reason)} onClick={() => void decide("rejected")}>Send back</button>
      </div>
    </section>
  );
}

function CaseInformation({ detail, onDone }: { detail: CaseDetail; onDone: () => Promise<void> }) {
  const [notes, setNotes] = useState("");
  const [product, setProduct] = useState("");
  const [batch, setBatch] = useState("");
  const [verdict, setVerdict] = useState("unconfirmed");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(close: boolean) {
    setBusy(true); setError("");
    try {
      if (close) await api.closeCase(detail.case.id, notes, verdict);
      else await api.addInformation(detail.case.id, notes, product, batch);
      setNotes(""); await onDone();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to save"); }
    finally { setBusy(false); }
  }
  return <section className="panel"><details><summary>Add investigation information or close the case</summary>
    <p className="muted">Saving information requires a new triage run and approval. Identity corrections are allowed before supermarket checks are assigned.</p>
    <label>New investigation facts (changes require fresh triage)<textarea value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
    {detail.inspections.length === 0 && <><label>Corrected product (optional)<input value={product} onChange={(event) => setProduct(event.target.value)} /></label><label>Corrected lot (optional)<input value={batch} onChange={(event) => setBatch(event.target.value)} /></label></>}
    <button className="button button-secondary" disabled={busy || notes.trim().length < 3} onClick={() => void save(false)}>Save facts — rerun triage required</button>
    {detail.manufacturer_response && <><label>Final human verdict<select value={verdict} onChange={(event) => setVerdict(event.target.value)}>{["unconfirmed", "suspected", "confirmed", "not_supported"].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label><button className="button button-primary" disabled={busy || notes.trim().length < 3} onClick={() => void save(true)}>Record verdict and close</button></>}
    {error && <div className="alert danger">{error}</div>}
  </details></section>;
}

function RetailerActions({ detail, inspections, onDone }: { detail: CaseDetail; inspections: Inspection[]; onDone: () => Promise<void> }) {
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [barcode, setBarcode] = useState("");
  const [match, setMatch] = useState<DemoBarcodeMatch | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const inspection = inspections.find((item) => item.case_id === detail.case.id);
  const needsVerification = detail.case.source === "customer_photo";

  async function lookup() {
    setBusy(true); setError(""); setMatch(null); setConfirmed(false);
    try { setMatch(await api.lookupBarcode(detail.case.id, barcode)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Barcode lookup failed"); }
    finally { setBusy(false); }
  }

  async function review(decision: string) {
    setBusy(true); setError("");
    try {
      await api.reviewCase(detail.case.id, decision, notes || "Packaging reviewed by supermarket officer.", match?.barcode);
      await onDone();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to forward case"); }
    finally { setBusy(false); }
  }
  async function finding(value: string) {
    if (!inspection) return;
    setBusy(true); setError("");
    try { await api.submitFinding(inspection.id, value, notes || "Stock inspected by retailer safety manager."); await onDone(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to record finding"); }
    finally { setBusy(false); }
  }

  if (inspection && inspection.status !== "completed") {
    return (
      <section className="panel approval-panel">
        <span className="eyebrow">Assigned inspection</span><h2>Record the human finding</h2>
        <label>Inspection notes<textarea rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
        {error && <div className="alert danger" role="alert">{error}</div>}
        <div className="action-row">
          <button className="button button-danger" disabled={busy} onClick={() => void finding("issue_observed")}>Issue observed</button>
          <button className="button button-secondary" disabled={busy} onClick={() => void finding("no_issue_observed")}>No issue observed</button>
          <button className="button button-ghost" disabled={busy} onClick={() => void finding("unable_to_assess")}>Unable to assess</button>
        </div>
      </section>
    );
  }
  if (!inspection && detail.retailer_review?.decision !== "forwarded") {
    return (
      <section className="panel approval-panel">
        <span className="eyebrow">Supermarket food safety officer</span><h2>Verify, then forward</h2>
        {needsVerification && <div className="verification-box">
          <div className="section-heading"><strong>Identify the product from the photo</strong><span className="pill pill-warning">Simulated barcode lookup</span></div>
          <p className="muted small">Review the uploaded packaging, then enter its demo code. This demo uses a fixed product and batch mapping; it does not decode images.</p>
          <label>Demo barcode<input value={barcode} placeholder="e.g. DEMO-CHOC-38" onChange={(event) => { setBarcode(event.target.value); setMatch(null); setConfirmed(false); }} /></label>
          <div className="action-row">
            <button className="button button-secondary" disabled={busy || !barcode.trim()} onClick={() => void lookup()}>{busy ? "Checking…" : "Look up demo barcode"}</button>
            <button className="button button-ghost" disabled={busy} onClick={() => { setBarcode("DEMO-CHOC-38"); setMatch(null); setConfirmed(false); }}>Use demo code</button>
          </div>
          {match && <div className="verified-match" role="status">
            <span className="eyebrow">Match from demo records</span><h3>{match.product_name}</h3>
            <div className="metric-row"><span><small>Product</small><strong>{match.sku}</strong></span><span><small>Manufacturer lot</small><strong>{match.batch_number}</strong></span></div>
            <label className="confirmation"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />I reviewed the photos and confirm this demo product and batch match.</label>
          </div>}
        </div>}
        <label>Review notes<textarea rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
        {error && <div className="alert danger" role="alert">{error}</div>}
        <div className="action-row">
          <button className="button button-primary" disabled={busy || (needsVerification && (!match || !confirmed))} onClick={() => void review("forwarded")}>Verify & forward to importer</button>
          <button className="button button-secondary" disabled={busy} onClick={() => void review("needs_customer_information")}>Request information</button>
        </div>
      </section>
    );
  }
  return null;
}

function ImportPanel({ onImported }: { onImported: () => Promise<void> }) {
  const [result, setResult] = useState("");
  const [rowErrors, setRowErrors] = useState<Record<string, unknown>[]>([]);
  const [busy, setBusy] = useState(false);
  async function upload(kind: "batches" | "shipments", file?: File) {
    if (!file) return;
    setBusy(true);
    try {
      const response = await api.importCsv(kind, file);
      setResult(`${label(kind)}: ${response.inserted} inserted, ${response.skipped} skipped, ${response.errors.length} errors.`);
      setRowErrors(response.errors);
      await onImported();
    } catch (reason) {
      setResult(reason instanceof Error ? reason.message : "Import failed");
      setRowErrors([]);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel compact-panel">
      <div><span className="eyebrow">Batch and shipment records</span><h2>Update tracking records</h2><p className="muted small">Import batches before shipments. Use codes from the organization list above.</p></div>
      <div className="import-grid">
        <label className="file-button">Batch CSV<input type="file" accept=".csv,text/csv" disabled={busy} onChange={(event) => void upload("batches", event.target.files?.[0])} /></label>
        <label className="file-button">Shipment CSV<input type="file" accept=".csv,text/csv" disabled={busy} onChange={(event) => void upload("shipments", event.target.files?.[0])} /></label>
        <a href="/api/v1/imports/templates/batches">Batch template</a>
        <a href="/api/v1/imports/templates/shipments">Shipment template</a>
      </div>
      {result && <p className="muted small">{result}</p>}
      {rowErrors.length > 0 && <ul className="import-errors">{rowErrors.map((item, index) => <li key={index}>Row {String(item.row)}: {String(item.error)}</li>)}</ul>}
    </section>
  );
}

function DataSetup() {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [batches, setBatches] = useState<BatchRecord[]>([]);
  const [shipments, setShipments] = useState<ShipmentRecord[]>([]);
  const [form, setForm] = useState({ code: "", name: "", type: "retailer" as "retailer" | "manufacturer", staff_name: "", staff_email: "", staff_password: "" });
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    const [nextOrganizations, nextBatches, nextShipments] = await Promise.all([api.organizations(), api.batches(), api.shipments()]);
    setOrganizations(nextOrganizations);
    setBatches(nextBatches);
    setShipments(nextShipments);
  }, []);
  useEffect(() => { void refresh().catch((error) => setMessage(String(error))); }, [refresh]);

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      await api.createOrganization(form);
      setMessage(`Created ${form.name} and its ${form.type} staff account (${form.staff_email}).`);
      setForm({ code: "", name: "", type: "retailer", staff_name: "", staff_email: "", staff_password: "" });
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not create organization");
    } finally {
      setBusy(false);
    }
  }

  return <main className="workspace data-setup">
    <header className="case-header"><div><span className="eyebrow">Importer records</span><h1>Data setup</h1><p>Add a manufacturer or retailer and its first staff login, then import batches followed by shipments.</p></div></header>
    {message && <div className="alert" role="status">{message}</div>}
    <section className="panel"><div className="section-heading"><div><span className="eyebrow">Organizations</span><h2>Add an organization</h2></div></div>
      <form className="data-form" onSubmit={(event) => void create(event)}>
        <label>Type<select value={form.type} onChange={(event) => setForm({ ...form, type: event.target.value as "retailer" | "manufacturer" })}><option value="retailer">Retailer</option><option value="manufacturer">Manufacturer</option></select></label>
        <label>Code<input required minLength={2} maxLength={40} pattern="[A-Za-z0-9][A-Za-z0-9_-]*" value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value.toUpperCase() })} placeholder="RETAILER-E" /></label>
        <label>Organization name<input required minLength={2} maxLength={200} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
        <label>Staff name<input required minLength={2} maxLength={120} value={form.staff_name} onChange={(event) => setForm({ ...form, staff_name: event.target.value })} /></label>
        <label>Staff email<input required type="email" value={form.staff_email} onChange={(event) => setForm({ ...form, staff_email: event.target.value })} /></label>
        <label>Initial password<input required type="password" minLength={12} maxLength={200} autoComplete="new-password" value={form.staff_password} onChange={(event) => setForm({ ...form, staff_password: event.target.value })} /></label>
        <button className="button button-primary" disabled={busy}>Create organization and login</button>
      </form>
      <p className="muted small">Share the initial password with the staff member privately. It is stored only as a hash.</p>
      <div className="record-list">{organizations.map((item) => <div key={item.id}><strong>{item.name}</strong><span>{item.code} · {label(item.type)}</span></div>)}</div>
    </section>
    <ImportPanel onImported={refresh} />
    <section className="panel"><span className="eyebrow">Current records</span><h2>Batches ({batches.length})</h2><div className="record-list">{batches.map((item) => <div key={item.id}><strong>{item.product_name} · Lot {item.batch_number}</strong><span>{item.sku} · {item.quantity_received} received</span></div>)}</div></section>
    <section className="panel"><h2>Shipments ({shipments.length})</h2><div className="record-list">{shipments.map((item) => <div key={item.id}><strong>{item.shipment_reference} · {item.retailer_name}</strong><span>{item.sku} · Lot {item.batch_number} · {item.quantity} shipped</span></div>)}</div></section>
  </main>;
}

function RetailerReportForm({ onCreated }: { onCreated: (created: CaseSummary) => void }) {
  const [products, setProducts] = useState<ProductRecord[]>([]);
  const [form, setForm] = useState({ product_name: "", batch_number: "", description: "", purchase_date: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { void api.products().then(setProducts).catch((reason) => setError(String(reason))); }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const created = await api.officerReport({
        product_name: form.product_name,
        batch_number: form.batch_number.trim(),
        description: form.description.trim(),
        ...(form.purchase_date ? { purchase_date: form.purchase_date } : {}),
      });
      onCreated(created);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create report");
    } finally {
      setBusy(false);
    }
  }

  return <main className="workspace data-setup"><header className="case-header"><div><span className="eyebrow">Retailer safety manager</span><h1>New inspection report</h1><p>Record a suspected issue for a product and manufacturer lot. This starts triage for importer review.</p></div></header>
    {error && <div className="alert danger" role="alert">{error}</div>}
    <section className="panel"><form className="data-form" onSubmit={(event) => void submit(event)}>
      <label>Product<select required value={form.product_name} onChange={(event) => setForm({ ...form, product_name: event.target.value })}><option value="">Select a product</option>{products.map((item) => <option key={item.id} value={item.sku}>{item.name} ({item.sku})</option>)}</select></label>
      <label>Manufacturer lot<input required maxLength={100} value={form.batch_number} onChange={(event) => setForm({ ...form, batch_number: event.target.value })} /></label>
      <label>Purchase date (optional)<input type="date" value={form.purchase_date} onChange={(event) => setForm({ ...form, purchase_date: event.target.value })} /></label>
      <label className="data-form-wide">Observed issue<textarea required minLength={10} maxLength={5000} rows={5} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
      <button className="button button-primary" disabled={busy || products.length === 0}>Submit suspected issue</button>
    </form></section>
  </main>;
}

function CaseWorkspace({ user, summary }: { user: User; summary: CaseSummary }) {
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [inspections, setInspections] = useState<Inspection[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    const next = await api.caseDetail(summary.id);
    setDetail(next);
    if (user.role === "retailer_safety_manager") setInspections(await api.inspections());
  }, [summary.id, user.role]);

  useEffect(() => { void refresh().catch((reason) => setError(String(reason))); }, [refresh]);

  useEffect(() => {
    if (!detail?.agent_runs.some((run) => ["queued", "running"].includes(run.status))) return;
    const timer = window.setTimeout(() => { void refresh().catch((reason) => setError(String(reason))); }, 1000);
    return () => window.clearTimeout(timer);
  }, [detail, refresh]);

  const latestRuns = useMemo(() => {
    const result: Partial<Record<AgentRun["agent_type"], AgentRun>> = {};
    for (const run of detail?.agent_runs ?? []) result[run.agent_type] = run;
    return result;
  }, [detail]);

  async function start(agent: AgentRun["agent_type"]) {
    setBusy(agent); setError("");
    try {
      await api.startAgent(summary.id, agent);
      await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Evidence check failed"); }
    finally { setBusy(""); }
  }

  if (!detail) return <div className="empty-state">Loading case evidence…</div>;
  const pending = detail.proposals.filter((proposal) => proposal.status === "pending" && Object.values(detail.workflow).some((step) => step.latest_proposal_id === proposal.id));
  const agentRunning = Boolean(busy) || detail.agent_runs.some((run) => ["queued", "running"].includes(run.status));
  const completedStages = (Object.keys(stageMeta) as AgentRun["agent_type"][]).filter((stage) => latestRuns[stage]?.status === "completed").length;
  const nextStage: AgentRun["agent_type"] | null = detail.workflow.escalation.can_run
    ? "escalation"
    : detail.workflow.traceability.can_run
      ? "traceability"
      : detail.workflow.triage.can_run
        ? "triage"
        : null;
  const availableOtherStages = (Object.keys(stageMeta) as AgentRun["agent_type"][]).filter((stage) => stage !== nextStage && detail.workflow[stage].can_run);

  return (
    <div className="workspace">
      <header className="case-header">
        <div><span className="eyebrow">Case {detail.case.public_id}</span><h1>{detail.case.product_name}</h1><p>{detail.description}</p></div>
        <div className="case-badges"><Pill value={detail.case.status} /><Pill value={detail.case.safety_verdict} /></div>
      </header>
      {error && <div className="alert danger">{error}</div>}
      {detail.demo_verification && <section className="panel verified-match">
        <span className="eyebrow">Human-verified product identity</span><h2>{detail.demo_verification.product_name}</h2>
        <p>Product {detail.demo_verification.sku} · Lot {detail.demo_verification.batch_number}</p>
        <span className="muted small">Confirmed by the supermarket officer using simulated code {detail.demo_verification.barcode}. See the timeline for the review record.</span>
      </section>}
      {detail.evidence.length > 0 && <section className="panel">
        <div className="section-heading"><div><span className="eyebrow">Customer evidence</span><h2>Packaging & reported issue</h2></div><span className="muted small">{detail.evidence.length} attachment(s)</span></div>
        <div className="evidence-grid">{detail.evidence.map((item) => <a key={item.id} href={item.url} target="_blank" rel="noreferrer" className="evidence-card">
          {item.content_type.startsWith("image/") ? <img src={item.url} alt={`Submitted evidence: ${item.filename}`} /> : <span>PDF evidence</span>}
          <span>{item.filename} ↗</span>
        </a>)}</div>
      </section>}
      {detail.case.source === "customer_photo" && detail.retailer_review?.decision !== "forwarded" && user.role === "importer_investigator" && <div className="alert" role="status">Awaiting supermarket officer verification. Product identification and tracing become available after the officer forwards the case.</div>}
      {user.role === "retailer_safety_manager" && <RetailerActions key={detail.case.id} detail={detail} inspections={inspections} onDone={refresh} />}
      <section>
        <div className="section-heading"><div><span className="eyebrow">Investigation progress</span><h2>Evidence checks</h2><p className="section-description">Complete each check in order. Every operational decision still requires human approval.</p></div><button className="button button-ghost" onClick={() => void refresh()}>Refresh status</button></div>
        <div className="progress-summary" aria-label={`${completedStages} of 3 evidence checks complete`}>
          <div><strong>{completedStages} of 3 complete</strong><span>{agentRunning ? "Checking evidence now" : nextStage ? `${stageMeta[nextStage].title} is ready` : pending.length ? "Waiting for your approval" : "Review requirements below"}</span></div>
          <div className="progress-track"><i style={{ width: `${(completedStages / 3) * 100}%` }} /></div>
        </div>
        <div className="agent-grid">
          <AgentCard agent="triage" run={latestRuns.triage} gate={detail.workflow.triage} />
          <AgentCard agent="traceability" run={latestRuns.traceability} gate={detail.workflow.traceability} />
          <AgentCard agent="escalation" run={latestRuns.escalation} gate={detail.workflow.escalation} />
        </div>
        {user.role === "importer_investigator" && nextStage && <div className="next-action-panel">
          <span className="next-action-icon">{stageMeta[nextStage].number}</span>
          <div><small>Recommended next action</small><h3>{stageMeta[nextStage].action}</h3><p>{stageMeta[nextStage].description}</p></div>
          <button className="button button-primary" disabled={agentRunning} onClick={() => void start(nextStage)}>{agentRunning ? "Working…" : stageMeta[nextStage].action}</button>
        </div>}
        {user.role === "importer_investigator" && availableOtherStages.length > 0 && <details className="other-actions"><summary>Other available checks</summary><div className="action-row">{availableOtherStages.map((stage) => <button key={stage} className="button button-secondary" disabled={agentRunning} onClick={() => void start(stage)}>{stageMeta[stage].action}</button>)}</div></details>}
      </section>
      {agentRunning && <div className="alert working-alert" role="status"><strong>Evidence check in progress</strong><span>This page updates automatically. You can stay here while records are checked.</span></div>}
      {user.role === "importer_investigator" && <>
        {Object.entries(detail.workflow).some(([, step]) => Boolean(step.blocked_reason)) && <section className="requirements-panel"><span className="eyebrow">What must happen next</span>{Object.entries(detail.workflow).map(([stage, step]) => step.blocked_reason && <div key={stage}><span>{stageMeta[stage as keyof typeof stageMeta].number}</span><p><strong>{stageMeta[stage as keyof typeof stageMeta].title}</strong>{stakeholderText(step.blocked_reason)}</p></div>)}</section>}
        {pending.map((proposal) => <ProposalReview key={proposal.id} proposal={proposal} caseId={detail.case.id} onDone={refresh} />)}
        {detail.case.status !== "closed" && <CaseInformation key={detail.case.id} detail={detail} onDone={refresh} />}
      </>}
      {detail.inspections.length > 0 && <section className="panel"><span className="eyebrow">Supermarket checks</span><h2>{detail.inspections.filter((item) => item.status === "completed").length} / {detail.inspections.length} responses received</h2>{detail.inspections.map((item) => <p key={item.id}><strong>{item.retailer_name}</strong> · {label(item.status)}{item.finding && ` · ${label(item.finding)}`}<br />{item.notes}</p>)}</section>}
      {detail.manufacturer_response && <section className="panel"><h2>Manufacturer response</h2><p>{detail.manufacturer_response}</p></section>}
      <section className="panel">
        <div className="section-heading"><div><span className="eyebrow">Audit trail</span><h2>Case timeline</h2></div><span className="muted">{detail.timeline.length} events</span></div>
        <div className="timeline">
          {detail.timeline.map((event) => <div className="timeline-item" key={event.id}><span className="timeline-dot" /><div><strong>{stakeholderText(label(event.event_type))}</strong><small>{formatDate(event.created_at)}</small></div></div>)}
        </div>
      </section>
    </div>
  );
}

function ManufacturerInbox() {
  const [items, setItems] = useState<Escalation[]>([]);
  const [selected, setSelected] = useState<Escalation | null>(null);
  const [response, setResponse] = useState("");
  const refresh = useCallback(async () => { const next = await api.escalations(); setItems(next); setSelected((current) => next.find((item) => item.id === current?.id) ?? next[0] ?? null); }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  async function submit() { if (!selected || !response.trim()) return; await api.respond(selected.id, response); setResponse(""); await refresh(); }
  return (
    <div className="manufacturer-grid">
      <aside className="case-list"><div className="list-heading"><span className="eyebrow">Manufacturer</span><h2>Escalations</h2></div>{items.map((item) => <button className={`case-row ${selected?.id === item.id ? "selected" : ""}`} key={item.id} onClick={() => setSelected(item)}><strong>{String(item.packet.case_public_id)}</strong><span>{String((item.packet.product as Record<string, unknown>)?.name ?? "Product")}</span><Pill value={item.status} /></button>)}</aside>
      <main className="workspace">{selected ? <><header className="case-header"><div><span className="eyebrow">Evidence packet</span><h1>{String(selected.packet.case_public_id)}</h1><p>Review the verified trace and retailer findings before responding.</p></div><Pill value={selected.status} /></header><section className="panel"><ManufacturerReport packet={selected.packet} downloadUrl={api.manufacturerReportUrl(selected.id)} /></section>{selected.status !== "responded" && <section className="panel approval-panel"><h2>Manufacturer response</h2><label>Investigation result<textarea rows={5} value={response} onChange={(event) => setResponse(event.target.value)} /></label><button className="button button-primary" onClick={() => void submit()}>Submit human response</button></section>}</> : <div className="empty-state">No manufacturer escalations yet.</div>}</main>
    </div>
  );
}

function StaffApp({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [selected, setSelected] = useState<CaseSummary | null>(null);
  const [view, setView] = useState<"cases" | "data" | "new-report">("cases");
  const nameStorageKey = `escalera.display-name.${user.id}`;
  const [displayName, setDisplayName] = useState(() => window.localStorage.getItem(nameStorageKey) || user.display_name);
  const [nameDraft, setNameDraft] = useState(displayName);
  const [settingsOpen, setSettingsOpen] = useState(false);
  useEffect(() => {
    if (user.role === "manufacturer_reviewer") return;
    void api.cases().then((items) => { setCases(items); setSelected(items[0] ?? null); });
  }, [user.role]);

  function saveDisplayName(event: FormEvent) {
    event.preventDefault();
    const nextName = nameDraft.trim();
    if (!nextName) return;
    window.localStorage.setItem(nameStorageKey, nextName);
    setDisplayName(nextName);
    setSettingsOpen(false);
  }

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <Brand className="brand-inverse" />
        <nav className="side-navigation" aria-label="Workspace">
          <span className="side-label">Workspace</span>
          <button type="button" className={`side-item ${view === "cases" ? "active" : ""}`} onClick={() => setView("cases")}><span className="side-icon"><InvestigationIcon /></span>{user.role === "manufacturer_reviewer" ? "Escalations" : "Investigations"}<i>{user.role === "manufacturer_reviewer" ? "" : cases.length}</i></button>
          {user.role === "importer_investigator" && <button type="button" className={`side-item ${view === "data" ? "active" : ""}`} onClick={() => setView("data")}><span className="side-icon"><SettingsIcon /></span>Data setup</button>}
          {user.role === "retailer_safety_manager" && <button type="button" className={`side-item ${view === "new-report" ? "active" : ""}`} onClick={() => setView("new-report")}><span className="side-icon"><InvestigationIcon /></span>New report</button>}
        </nav>
        <div className="sidebar-account">
          {settingsOpen && <form className="account-popover" id="account-settings" onSubmit={saveDisplayName}>
            <div className="account-popover-head"><strong>Account settings</strong><button type="button" onClick={() => setSettingsOpen(false)} aria-label="Close settings">×</button></div>
            <label>Display name<input maxLength={60} value={nameDraft} onChange={(event) => setNameDraft(event.target.value)} /></label>
            <button className="button button-primary">Save name</button>
            <button type="button" className="button button-secondary" onClick={onLogout}>Log out</button>
          </form>}
          <div className="sidebar-user"><span>{displayName.slice(0, 2).toUpperCase()}</span><div className="sidebar-identity"><strong>{displayName}</strong><small>{label(user.role)}</small></div><button className="settings-toggle" onClick={() => setSettingsOpen((open) => !open)} aria-label="Open account settings" aria-expanded={settingsOpen} aria-controls="account-settings"><SettingsIcon /></button></div>
        </div>
      </aside>
      <div className="app-surface">
        <header className="app-bar"><div><span className="app-kicker">Operations console</span><strong>{user.role === "manufacturer_reviewer" ? "Manufacturer review" : "Food safety investigations"}</strong></div><div className="bar-actions"><span className="live-indicator"><i /> Live records</span></div></header>
        {user.role === "importer_investigator" && view === "data" ? <DataSetup /> : user.role === "retailer_safety_manager" && view === "new-report" ? <RetailerReportForm onCreated={(created) => { setCases((items) => [created, ...items]); setSelected(created); setView("cases"); }} /> : user.role === "manufacturer_reviewer" ? <ManufacturerInbox /> : (
          <div className="dashboard-grid">
            <aside className="case-list"><div className="list-heading"><span className="eyebrow">Operational queue</span><h2>Cases</h2><span>{cases.length} active records</span></div>{cases.map((item) => <button className={`case-row ${selected?.id === item.id ? "selected" : ""}`} key={item.id} onClick={() => setSelected(item)}><div><strong>{item.public_id}</strong><span>{item.reporter_name ?? item.product_name}</span></div><Pill value={item.status} /><small>{item.product_name} · Lot {item.batch_number ?? "unknown"}</small></button>)}</aside>
            <main>{selected ? <CaseWorkspace user={user} summary={selected} /> : <div className="empty-state">No cases are available for this organization.</div>}</main>
          </div>
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [screen, setScreen] = useState<"public" | "login">("public");
  const [loading, setLoading] = useState(true);
  useEffect(() => { void api.me().then(setUser).catch(() => undefined).finally(() => setLoading(false)); }, []);
  async function logout() { await api.logout(); setUser(null); setScreen("public"); }
  const publicPage = window.location.pathname.replace(/\/$/, "");
  if (publicPage === "/how-it-works" || publicPage === "/safety-controls") {
    return <PublicInfoPage page={publicPage.slice(1) as "how-it-works" | "safety-controls"} onLogin={() => {
      window.history.replaceState(null, "", "/");
      setScreen("login");
    }} />;
  }
  if (loading) return <div className="loading-screen"><Brand className="brand-large" markOnly /><p>Loading trusted records…</p></div>;
  if (user) return <StaffApp user={user} onLogout={() => void logout()} />;
  if (screen === "login") return <Login onSuccess={setUser} onBack={() => setScreen("public")} />;
  return <PublicReport onLogin={() => setScreen("login")} />;
}
