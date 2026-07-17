import { useEffect, useMemo, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

declare global { interface Window { __CUSTOMERPULSE_CONFIG__?: { API_URL?: string } } }
const API = window.__CUSTOMERPULSE_CONFIG__?.API_URL || import.meta.env.VITE_API_URL || "http://localhost:8000";
const call = async (path: string, options?: RequestInit) => {
  const response = await fetch(`${API}${path}`, options);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
};
const money = (value: number) => new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(value || 0);
const pct = (value: number) => `${Math.round((value || 0) * 100)}%`;
type Tab = "overview" | "workspace" | "customers" | "campaigns" | "audit";

function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [dashboard, setDashboard] = useState<any>(null);
  const [customers, setCustomers] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [investigations, setInvestigations] = useState<any[]>([]);
  const [approvals, setApprovals] = useState<any[]>([]);
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [audits, setAudits] = useState<any[]>([]);
  const [targets, setTargets] = useState<Record<number, any[]>>({});
  const [expandedCampaign, setExpandedCampaign] = useState<number | null>(null);
  const [query, setQuery] = useState("Show top 5 customers by lifetime value");
  const [agentResult, setAgentResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");

  const refresh = async () => {
    try {
      const [summary, customerRows, productRows, runs, gates, campaignRows, logs] = await Promise.all([
        call("/api/dashboard"), call("/api/customers?limit=100"), call("/api/products"), call("/api/investigations"),
        call("/api/approvals"), call("/api/campaigns"), call("/api/audit-events"),
      ]);
      setDashboard(summary); setCustomers(customerRows); setProducts(productRows); setInvestigations(runs);
      setApprovals(gates); setCampaigns(campaignRows); setAudits(logs); setError("");
    } catch { setError("The live API is unavailable. Check the Render backend deployment and refresh."); }
  };
  useEffect(() => { refresh(); }, []);

  const execute = async (prompt = query) => {
    if (prompt.trim().length < 3) return;
    setQuery(prompt); setAgentResult(null); setBusy(true); setError(""); setTab("workspace");
    try {
      const response = await call("/api/investigations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ goal: prompt }) });
      if (response.status === "failed") throw new Error(response.error || "Agent execution failed");
      setAgentResult(response); await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Agent request failed"); }
    finally { setBusy(false); }
  };
  const decide = async (id: number, approved: boolean) => {
    try { await call(`/api/approvals/${id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approved, decided_by: "dashboard-manager" }) }); await refresh(); }
    catch { setError("The approval could not be saved."); }
  };
  const toggleTargets = async (campaignId: number) => {
    if (expandedCampaign === campaignId) return setExpandedCampaign(null);
    setExpandedCampaign(campaignId);
    if (!targets[campaignId]) setTargets(previous => ({ ...previous, [campaignId]: [] }));
    try { const rows = await call(`/api/campaigns/${campaignId}/targets`); setTargets(previous => ({ ...previous, [campaignId]: rows })); }
    catch { setError("Campaign targets could not be loaded."); }
  };
  const filteredCustomers = useMemo(() => customers.filter(item => `${item.external_id} ${item.country} ${item.segment}`.toLowerCase().includes(search.toLowerCase())), [customers, search]);
  const pending = approvals.filter(item => item.status === "pending");

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">CP</div><div><strong>CustomerPulse</strong><span>Agent Operations</span></div></div>
      <nav>
        <Nav active={tab === "overview"} onClick={() => setTab("overview")} icon="⌂">Overview</Nav>
        <Nav active={tab === "workspace"} onClick={() => setTab("workspace")} icon="✦">Agent workspace</Nav>
        <Nav active={tab === "customers"} onClick={() => setTab("customers")} icon="◉">Customers</Nav>
        <Nav active={tab === "campaigns"} onClick={() => setTab("campaigns")} icon="◇">Campaigns <em>{pending.length}</em></Nav>
        <Nav active={tab === "audit"} onClick={() => setTab("audit")} icon="≡">Audit trail</Nav>
      </nav>
      <div className="system-status"><i></i><div><strong>System operational</strong><span>Groq · LangGraph · MCP</span></div></div>
    </aside>
    <main className="content">
      <header className="topbar"><div><p className="kicker">CUSTOMER INTELLIGENCE PLATFORM</p><h1>{tab === "overview" ? "Operations overview" : tab === "workspace" ? "Multi-agent workspace" : tab[0].toUpperCase() + tab.slice(1)}</h1></div><button className="secondary" onClick={refresh}>↻ Refresh</button></header>
      {error && <div className="alert"><b>Action needed</b><span>{error}</span><button onClick={() => setError("")}>×</button></div>}
      {tab === "overview" && <Overview dashboard={dashboard} investigations={investigations} campaigns={campaigns} pending={pending} products={products} execute={execute} />}
      {tab === "workspace" && <Workspace query={query} setQuery={setQuery} clearResult={() => setAgentResult(null)} execute={execute} busy={busy} response={agentResult} investigations={investigations} />}
      {tab === "customers" && <Customers rows={filteredCustomers} search={search} setSearch={setSearch} execute={execute} />}
      {tab === "campaigns" && <Campaigns campaigns={campaigns} approvals={approvals} targets={targets} expanded={expandedCampaign} toggle={toggleTargets} decide={decide} />}
      {tab === "audit" && <Audit rows={audits} />}
    </main>
  </div>;
}

function Overview({ dashboard, investigations, campaigns, pending, products, execute }: any) {
  return <>
    <section className="metrics-row">
      <Metric label="Customers" value={dashboard?.customers ?? "—"} note="Profiles in PostgreSQL" tone="blue"/>
      <Metric label="Orders" value={dashboard?.orders ?? "—"} note="Imported transactions" tone="violet"/>
      <Metric label="High churn risk" value={dashboard?.high_risk_customers ?? "—"} note="Risk score ≥ 65%" tone="amber"/>
      <Metric label="Pending approvals" value={dashboard?.pending_approvals ?? "—"} note="Human decision required" tone="green"/>
    </section>
    <section className="quick-section"><div className="section-heading"><div><p className="kicker">QUICK ACTIONS</p><h2>Ask the specialist agents</h2></div><span>Read-only requests never create campaigns</span></div>
      <div className="quick-grid">
        <Quick title="Top customers" text="Rank customers by lifetime purchase value." prompt="Show top 5 customers by lifetime value" execute={execute}/>
        <Quick title="Customer profile" text="Inspect risk, segment, country and value." prompt="Show customer 16244 details" execute={execute}/>
        <Quick title="Purchase history" text="Retrieve recent invoices for one customer." prompt="Show purchase history for customer 16244" execute={execute}/>
        <Quick title="Churn analysis" text="Let three agents investigate risk evidence." prompt="Analyze the top 10 customers at churn risk" execute={execute}/>
      </div>
    </section>
    <section className="two-col">
      <Card title="Recent agent runs" eyebrow="LANGGRAPH EXECUTIONS"><RunList rows={investigations.slice(0, 6)}/></Card>
      <Card title="Campaign control" eyebrow="HUMAN-IN-THE-LOOP"><div className="campaign-summary"><strong>{campaigns.length}</strong><span>campaigns created</span><strong>{pending.length}</strong><span>awaiting approval</span></div><p className="muted">Campaigns contain exact customer targets. Active or draft targets are excluded from new campaigns.</p></Card>
    </section>
  </>;
}

function Workspace({ query, setQuery, clearResult, execute, busy, response, investigations }: any) {
  const examples = ["Show top 5 customers by lifetime value", "Show customer 16244 details", "Show purchase history for customer 16244", "Show customers in France", "Analyze churn risk", "Create a retention campaign for 10 high-value customers"];
  return <>
    <section className="command-card"><div className="command-title"><div className="agent-orb">✦</div><div><h2>Ask CustomerPulse</h2><p>Supervisor routes your request to the correct specialist agents.</p></div></div>
      <div className="command-box"><textarea value={query} onChange={event => { setQuery(event.target.value); clearResult(); }} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); execute(); } }} placeholder="Ask about customers, purchases, locations, churn, or explicitly create a campaign…"/><button disabled={busy} onClick={() => execute()}>{busy ? "Agents working…" : "Run request →"}</button></div>
      <div className="chips">{examples.map(item => <button key={item} onClick={() => execute(item)}>{item}</button>)}</div>
    </section>
    {busy && <section className="working"><i></i><div><b>Multi-agent workflow is running</b><span>Supervisor → Customer Intelligence → Product Intelligence → Memory → Response</span></div></section>}
    {response && !busy && <Result response={response}/>}
    <Card title="Execution history" eyebrow="OBSERVABLE AGENT RUNS"><RunList rows={investigations.slice(0, 10)}/></Card>
  </>;
}

function Result({ response }: any) {
  const result = response.result || {}; const data = result.data || {};
  const customers = data.customers || [];
  return <section className="result-card"><div className="result-head"><div><span className="status-dot"></span><b>Request completed</b><p>{result.summary}</p></div><Badge value={response.intent || result.kind}/></div>
    {result.agents && <div className="agent-chain">{result.agents.map((agent: string, index: number) => <span key={agent}>{agent}{index < result.agents.length - 1 && <i>→</i>}</span>)}</div>}
    {customers.length > 0 && <CustomerTable rows={customers}/>}
    {result.kind === "customer_detail" && <Profile data={data}/>}
    {result.kind === "purchase_history" && <><Profile data={data.customer}/><OrderTable rows={data.orders || []}/></>}
    {result.kind === "campaign" && <div className="campaign-result"><strong>{result.created ? result.target_count : 0}</strong><span>{result.created ? "unique customers selected" : "campaigns created"}</span>{result.created && <><b>{result.excluded_existing_targets} duplicate targets excluded</b><p>Campaign #{result.campaign_id} is a draft awaiting human approval.</p></>}</div>}
  </section>;
}

function Customers({ rows, search, setSearch, execute }: any) {
  return <Card title="Customer directory" eyebrow="LIVE POSTGRESQL DATA" action={<input className="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search ID, country, segment…"/>}>
    <div className="table-wrap"><table><thead><tr><th>Customer</th><th>Country</th><th>Segment</th><th>Churn risk</th><th>Lifetime value</th><th></th></tr></thead><tbody>{rows.map((item: any) => <tr key={item.id}><td><b>{item.external_id}</b></td><td>{item.country}</td><td><Badge value={item.segment}/></td><td><Risk value={item.churn_risk}/></td><td><b>{money(item.lifetime_value)}</b></td><td><button className="link" onClick={() => execute(`Show customer ${item.external_id} details`)}>View profile →</button></td></tr>)}</tbody></table></div>
  </Card>;
}

function Campaigns({ campaigns, approvals, targets, expanded, toggle, decide }: any) {
  const approvalFor = (id: number) => approvals.find((item: any) => item.campaign_id === id);
  return <div className="campaign-list">{campaigns.length === 0 && <Card title="No campaigns yet"><p className="muted">Explicitly request a campaign from the Agent workspace.</p></Card>}{campaigns.map((campaign: any) => { const approval = approvalFor(campaign.id); const rows = targets[campaign.id] || []; return <section className="campaign-card" key={campaign.id}>
    <div className="campaign-main"><div><div className="campaign-title"><span>Campaign #{campaign.id}</span><Badge value={campaign.status}/></div><h2>{campaign.name}</h2><p>{campaign.offer} · Segment: {campaign.segment}</p></div><div className="target-total"><strong>{campaign.target_count}</strong><span>target customers</span></div></div>
    <div className="campaign-actions"><button className="secondary" onClick={() => toggle(campaign.id)}>{expanded === campaign.id ? "Hide customers" : `View ${campaign.target_count} customers`}</button>{approval?.status === "pending" && <><button className="approve" onClick={() => decide(approval.id, true)}>Approve campaign</button><button className="reject" onClick={() => decide(approval.id, false)}>Reject</button></>} {approval && approval.status !== "pending" && <span className="decision">Decision: <b>{approval.status}</b>{approval.decided_by ? ` by ${approval.decided_by}` : ""}</span>}</div>
    {expanded === campaign.id && <div className="target-panel">{campaign.target_count === 0 ? <p className="muted">Legacy segment-level campaign: no individual targets were recorded.</p> : rows.length === 0 ? <p className="muted">Loading targets…</p> : <CustomerTable rows={rows}/>}</div>}
  </section>; })}</div>;
}

function Audit({ rows }: any) { return <Card title="MCP tool audit trail" eyebrow="TRACEABLE AGENT ACTIONS"><div className="audit-list">{rows.map((item: any) => <article key={item.id}><div><span className="tool-icon">M</span><b>{item.tool}</b></div><time>{new Date(item.created_at).toLocaleString()}</time><code>{JSON.stringify(item.output)}</code></article>)}</div></Card>; }
function RunList({ rows }: any) { return <div className="run-list">{rows.length === 0 && <p className="muted">No agent runs yet.</p>}{rows.map((item: any) => <article key={item.id}><span className={`run-status ${item.status}`}></span><div><b>#{item.id} · {item.goal}</b><small>{(item.plan || []).join(" → ")}</small></div><Badge value={item.status}/></article>)}</div>; }
function CustomerTable({ rows }: any) { return <div className="table-wrap result-table"><table><thead><tr><th>Customer ID</th><th>Country / Segment</th><th>Risk</th><th>Lifetime value</th></tr></thead><tbody>{rows.map((item: any) => <tr key={item.id || item.customer_id}><td><b>{item.external_id}</b></td><td>{item.country || item.segment || "—"}<small>{item.country && item.segment ? item.segment : ""}</small></td><td>{pct(item.risk ?? item.churn_risk)}</td><td><b>{money(item.lifetime_value ?? item.ltv)}</b></td></tr>)}</tbody></table></div>; }
function OrderTable({ rows }: any) { return <div className="table-wrap result-table"><table><thead><tr><th>Invoice</th><th>Date</th><th>Status</th><th>Total</th></tr></thead><tbody>{rows.map((item: any) => <tr key={item.invoice}><td><b>{item.invoice}</b></td><td>{new Date(item.date).toLocaleDateString()}</td><td><Badge value={item.status}/></td><td>{money(item.total)}</td></tr>)}</tbody></table></div>; }
function Profile({ data }: any) { return <div className="profile-grid"><div><span>Customer ID</span><b>{data.external_id}</b></div><div><span>Country</span><b>{data.country || "—"}</b></div><div><span>Segment</span><Badge value={data.segment}/></div><div><span>Churn risk</span><b>{pct(data.risk ?? data.churn_risk)}</b></div><div><span>Lifetime value</span><b>{money(data.lifetime_value)}</b></div><div><span>Last purchase</span><b>{data.last_purchase_at ? new Date(data.last_purchase_at).toLocaleDateString() : "—"}</b></div></div>; }
function Metric({ label, value, note, tone }: any) { return <article className={`metric ${tone}`}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>; }
function Quick({ title, text, prompt, execute }: any) { return <button className="quick-card" onClick={() => execute(prompt)}><span>✦</span><div><b>{title}</b><p>{text}</p></div><i>→</i></button>; }
function Risk({ value }: any) { return <div className="risk"><span><i style={{ width: `${Math.round(value * 100)}%` }}></i></span><b>{pct(value)}</b></div>; }
function Badge({ value }: { value: string }) { return <span className={`badge ${String(value).replaceAll("_", "-")}`}>{String(value).replaceAll("_", " ")}</span>; }
function Nav({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: string; children: ReactNode }) { return <button className={active ? "active" : ""} onClick={onClick}><span>{icon}</span>{children}</button>; }
function Card({ title, eyebrow, action, children }: { title: string; eyebrow?: string; action?: ReactNode; children: ReactNode }) { return <section className="card"><div className="card-head"><div>{eyebrow && <p className="kicker">{eyebrow}</p>}<h2>{title}</h2></div>{action}</div>{children}</section>; }

createRoot(document.getElementById("root")!).render(<App/>);
