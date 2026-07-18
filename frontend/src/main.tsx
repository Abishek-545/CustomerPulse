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
type Tab = "overview" | "workspace" | "customers" | "campaigns" | "guide" | "audit";

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
        <Nav active={tab === "guide"} onClick={() => setTab("guide")} icon="?">How it works</Nav>
        <Nav active={tab === "audit"} onClick={() => setTab("audit")} icon="≡">Audit trail</Nav>
      </nav>
      <div className="system-status"><i></i><div><strong>System operational</strong><span>Groq · LangGraph · MCP</span></div></div>
    </aside>
    <main className="content">
      <header className="topbar"><div><p className="kicker">CUSTOMER INTELLIGENCE PLATFORM</p><h1>{tab === "overview" ? "Operations overview" : tab === "workspace" ? "Multi-agent workspace" : tab === "guide" ? "How CustomerPulse works" : tab[0].toUpperCase() + tab.slice(1)}</h1></div><button className="secondary" onClick={refresh}>↻ Refresh</button></header>
      {error && <div className="alert"><b>Action needed</b><span>{error}</span><button onClick={() => setError("")}>×</button></div>}
      {tab === "overview" && <Overview dashboard={dashboard} investigations={investigations} campaigns={campaigns} pending={pending} products={products} execute={execute} />}
      {tab === "workspace" && <Workspace query={query} setQuery={setQuery} clearResult={() => setAgentResult(null)} execute={execute} busy={busy} response={agentResult} investigations={investigations} />}
      {tab === "customers" && <Customers rows={filteredCustomers} search={search} setSearch={setSearch} execute={execute} />}
      {tab === "campaigns" && <Campaigns dashboard={dashboard} campaigns={campaigns} approvals={approvals} targets={targets} expanded={expandedCampaign} toggle={toggleTargets} decide={decide} />}
      {tab === "guide" && <Guide execute={execute}/>}
      {tab === "audit" && <Audit rows={audits} />}
    </main>
  </div>;
}

function Overview({ dashboard, investigations, campaigns, pending, products, execute }: any) {
  return <>
    <section className="intro-card"><div><p className="kicker">WHAT THIS APP DOES</p><h2>Turn customer purchase history into explainable retention actions</h2><p>CustomerPulse helps an operations manager find valuable customers who may not return, understand the evidence, and prepare a safe retention campaign. Customer-facing actions remain drafts until a person approves them.</p></div><button className="secondary" onClick={() => execute("Explain what this app does and the role of each agent")}>Ask how it works →</button></section>
    <section className="metrics-row">
      <Metric label="Customer records" value={dashboard?.customers ?? "—"} note="Profiles stored in PostgreSQL" tone="blue"/>
      <Metric label="Invoices" value={dashboard?.orders ?? "—"} note="Unique purchase invoices" tone="violet"/>
      <Metric label="Likely not to return" value={dashboard?.high_risk_customers ?? "—"} note="Inactivity risk score ≥ 65%" tone="amber"/>
      <Metric label="Eligible for retention" value={dashboard?.eligible_retention_customers ?? "—"} note="High-value, high-risk, not targeted" tone="violet"/>
      <Metric label="Pending approvals" value={dashboard?.pending_approvals ?? "—"} note="Human decision required" tone="green"/>
    </section>
    <section className="quick-section"><div className="section-heading"><div><p className="kicker">QUICK ACTIONS</p><h2>Ask the specialist agents</h2></div><span>Read-only requests never create campaigns</span></div>
      <div className="quick-grid">
        <Quick title="Top customers" text="Rank customers by lifetime purchase value." prompt="Show top 5 customers by lifetime value" execute={execute}/>
        <Quick title="Customer profile" text="Inspect risk, segment, country and value." prompt="Show customer 16244 details" execute={execute}/>
        <Quick title="Purchase history" text="Retrieve recent invoices for one customer." prompt="Show purchase history for customer 16244" execute={execute}/>
        <Quick title="Churn analysis" text="Let three agents investigate risk evidence." prompt="Analyze the top 10 customers at churn risk" execute={execute}/>
        <Quick title="Explain CustomerPulse" text="Learn the metrics, agents, and safety rules." prompt="What does this app do, what do its metrics mean, and what is the role of each agent?" execute={execute}/>
      </div>
    </section>
    <section className="two-col">
      <Card title="Recent agent runs" eyebrow="LANGGRAPH EXECUTIONS"><RunList rows={investigations.slice(0, 6)}/></Card>
      <Card title="Campaign capacity" eyebrow="HUMAN-IN-THE-LOOP"><div className="campaign-summary"><strong>{dashboard?.eligible_retention_customers ?? "—"}</strong><span>customers still eligible</span><strong>{dashboard?.currently_targeted_customers ?? "—"}</strong><span>already in draft or active campaigns</span></div><p className="muted">Every new campaign selects different eligible customers. When the remaining count reaches zero, the agent safely creates no campaign. New purchase data or closed campaigns can make customers eligible again.</p></Card>
    </section>
  </>;
}

function Workspace({ query, setQuery, clearResult, execute, busy, response, investigations }: any) {
  const examples = ["What does this app do?", "Explain churn risk, lifetime value, and customer segments", "Show top 5 customers by lifetime value", "Show customer 16244 details", "Show purchase history for customer 16244", "Show customers in France", "Analyze churn risk", "Create a retention campaign for 10 high-value customers"];
  return <>
    <section className="command-card"><div className="command-title"><div className="agent-orb">✦</div><div><h2>Ask CustomerPulse</h2><p>Supervisor routes your request to the correct specialist agents.</p></div></div>
      <div className="command-box"><textarea value={query} onChange={event => { setQuery(event.target.value); clearResult(); }} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); execute(); } }} placeholder="Ask what the app does, what a metric means, or ask about customers, purchases, risk and campaigns…"/><button disabled={busy} onClick={() => execute()}>{busy ? "Agents working…" : "Run request →"}</button></div>
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
    {result.kind === "help" && <HelpResult data={data}/>}
    {result.kind === "campaign" && <div className="campaign-result"><strong>{result.created ? result.target_count : 0}</strong><span>{result.created ? "unique customers selected" : "campaigns created"}</span>{result.created && <><b>{result.excluded_existing_targets} duplicate targets excluded</b><p>Campaign #{result.campaign_id} is a draft awaiting human approval.</p></>}</div>}
  </section>;
}

function Customers({ rows, search, setSearch, execute }: any) {
  return <Card title="Customer health and value" eyebrow="LIVE POSTGRESQL DATA" action={<input className="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search customer ID, country, or group…"/>}>
    <p className="table-explainer">Risk is an explainable inactivity score derived from recency, purchase frequency, cancellations, and spending. It is not a confirmed cancellation prediction.</p>
    <div className="table-wrap"><table><thead><tr><th>Customer ID</th><th>Country</th><th>Customer group</th><th title="Estimated likelihood that the customer will not return, based on historical behavior">Likelihood of not returning</th><th title="Total net amount this customer spent in the imported purchase history">Total customer spend</th><th></th></tr></thead><tbody>{rows.map((item: any) => <tr key={item.id}><td><b>{item.external_id}</b></td><td>{item.country}</td><td><Badge value={item.segment}/></td><td><Risk value={item.churn_risk}/></td><td><b>{money(item.lifetime_value)}</b></td><td><button className="link" onClick={() => execute(`Show customer ${item.external_id} details`)}>View profile →</button></td></tr>)}</tbody></table></div>
  </Card>;
}

function Campaigns({ dashboard, campaigns, approvals, targets, expanded, toggle, decide }: any) {
  const approvalFor = (id: number) => approvals.find((item: any) => item.campaign_id === id);
  return <div className="campaign-list"><section className="capacity-card"><div><span>Eligible customers remaining</span><strong>{dashboard?.eligible_retention_customers ?? "—"}</strong></div><div><span>Customers protected from duplicate targeting</span><strong>{dashboard?.currently_targeted_customers ?? "—"}</strong></div><p>Draft and active campaigns reserve their exact customers. When no eligible customers remain, the agent returns a safe “no campaign created” result instead of selecting the same people again.</p></section>{campaigns.length === 0 && <Card title="No campaigns yet"><p className="muted">Explicitly request a campaign from the Agent workspace.</p></Card>}{campaigns.map((campaign: any) => { const approval = approvalFor(campaign.id); const rows = targets[campaign.id] || []; return <section className="campaign-card" key={campaign.id}>
    <div className="campaign-main"><div><div className="campaign-title"><span>Campaign #{campaign.id}</span><Badge value={campaign.status}/></div><h2>{campaign.name}</h2><p>{campaign.offer} · Segment: {campaign.segment}</p></div><div className="target-total"><strong>{campaign.target_count}</strong><span>target customers</span></div></div>
    <div className="campaign-actions"><button className="secondary" onClick={() => toggle(campaign.id)}>{expanded === campaign.id ? "Hide customers" : `View ${campaign.target_count} customers`}</button>{approval?.status === "pending" && <><button className="approve" onClick={() => decide(approval.id, true)}>Approve campaign</button><button className="reject" onClick={() => decide(approval.id, false)}>Reject</button></>} {approval && approval.status !== "pending" && <span className="decision">Decision: <b>{approval.status}</b>{approval.decided_by ? ` by ${approval.decided_by}` : ""}</span>}</div>
    {expanded === campaign.id && <div className="target-panel">{campaign.target_count === 0 ? <p className="muted">Legacy segment-level campaign: no individual targets were recorded.</p> : rows.length === 0 ? <p className="muted">Loading targets…</p> : <CustomerTable rows={rows}/>}</div>}
  </section>; })}</div>;
}

function Guide({ execute }: any) {
  const agents = [
    ["Supervisor", "Understands the request, chooses a safe intent, and routes work to specialists."],
    ["Customer Intelligence", "Queries customer profiles, purchases, locations, spend, and inactivity risk through MCP tools."],
    ["Product Intelligence", "Checks product returns, cancellations, and demand signals when they are relevant."],
    ["Memory", "Retrieves prior campaign outcomes and stores useful lessons for later runs."],
    ["Campaign & Safety", "Selects unique eligible customers, creates a draft, and pauses for human approval."],
    ["Response", "Combines the agents' evidence into one clear result with an auditable execution chain."],
  ];
  return <div className="guide-page">
    <section className="guide-hero"><p className="kicker">PLAIN-ENGLISH PRODUCT GUIDE</p><h2>CustomerPulse finds retention opportunities without silently acting on customers</h2><p>It analyzes real PostgreSQL customer and invoice records, lets specialist agents answer operational questions, and creates customer-specific retention drafts only when you explicitly request a campaign.</p><button onClick={() => execute("Explain what this app does, its metrics, campaign rules, and every agent role")}>Ask the agents to explain it →</button></section>
    <section><div className="section-heading"><div><p className="kicker">METRIC DEFINITIONS</p><h2>What the customer columns mean</h2></div></div><div className="definition-grid">
      <Definition title="Total customer spend" technical="Lifetime value (LTV)" text="The customer's total net spend in the imported transaction history. Example: £1,056 means the recorded purchases minus cancellations total £1,056."/>
      <Definition title="Likelihood of not returning" technical="Churn risk" text="A 0–95% rule-based inactivity score using recency, frequency, cancellations, and spending. It is an explainable warning, not a guaranteed prediction."/>
      <Definition title="Customer group" technical="Segment" text="A business label derived from value and risk. ‘High-value customer at risk’ means the customer has spent relatively more and also shows strong inactivity signals."/>
    </div></section>
    <section className="card"><div className="card-head"><div><p className="kicker">MULTI-AGENT ARCHITECTURE</p><h2>Why several agents are used</h2></div></div><p className="table-explainer">Each agent owns a narrow responsibility and MCP tool set. The LangGraph supervisor coordinates them, shares evidence through graph state, and preserves checkpoints so the workflow is observable instead of one opaque LLM call.</p><div className="agent-role-list">{agents.map(([name, text]) => <article key={name}><b>{name}</b><p>{text}</p></article>)}</div></section>
    <section className="policy-note"><b>What happens when campaign customers run out?</b><p>Every draft or active campaign reserves exact customer IDs, so a later campaign cannot target them again. With a static dataset, the eligible count eventually reaches zero and no campaign is created. Importing newer purchases, completing campaigns, or changing eligibility policy can replenish the pool.</p></section>
  </div>;
}

function Definition({ title, technical, text }: any) { return <article className="definition-card"><span>{technical}</span><h3>{title}</h3><p>{text}</p></article>; }
function HelpResult({ data }: any) { return <div className="help-result"><div className="help-answer"><h3>CustomerPulse explained</h3><p>{data.answer}</p></div><div className="definition-grid">{(data.definitions || []).map((item: any) => <Definition key={item.term} title={item.plain_name} technical={item.term} text={`${item.meaning} ${item.example || ""}`}/>)}</div><div className="agent-role-list">{(data.agents || []).map((item: any) => <article key={item.name}><b>{item.name}</b><p>{item.role}</p></article>)}</div>{data.campaign_policy && <div className="policy-note"><b>Campaign safety and capacity</b><p>{data.campaign_policy}</p></div>}</div>; }

function Audit({ rows }: any) { return <Card title="MCP tool audit trail" eyebrow="TRACEABLE AGENT ACTIONS"><div className="audit-list">{rows.map((item: any) => <article key={item.id}><div><span className="tool-icon">M</span><b>{item.tool}</b></div><time>{new Date(item.created_at).toLocaleString()}</time><code>{JSON.stringify(item.output)}</code></article>)}</div></Card>; }
function RunList({ rows }: any) { return <div className="run-list">{rows.length === 0 && <p className="muted">No agent runs yet.</p>}{rows.map((item: any) => <article key={item.id}><span className={`run-status ${item.status}`}></span><div><b>#{item.id} · {item.goal}</b><small>{(item.plan || []).join(" → ")}</small></div><Badge value={item.status}/></article>)}</div>; }
function CustomerTable({ rows }: any) { return <div className="table-wrap result-table"><table><thead><tr><th>Customer ID</th><th>Country / customer group</th><th>Likelihood of not returning</th><th>Total customer spend</th></tr></thead><tbody>{rows.map((item: any) => <tr key={item.id || item.customer_id}><td><b>{item.external_id}</b></td><td>{item.country || friendlySegment(item.segment) || "—"}<small>{item.country && item.segment ? friendlySegment(item.segment) : ""}</small></td><td>{pct(item.risk ?? item.churn_risk)}</td><td><b>{money(item.lifetime_value ?? item.ltv)}</b></td></tr>)}</tbody></table></div>; }
function OrderTable({ rows }: any) { return <div className="table-wrap result-table"><table><thead><tr><th>Invoice</th><th>Date</th><th>Status</th><th>Total</th></tr></thead><tbody>{rows.map((item: any) => <tr key={item.invoice}><td><b>{item.invoice}</b></td><td>{new Date(item.date).toLocaleDateString()}</td><td><Badge value={item.status}/></td><td>{money(item.total)}</td></tr>)}</tbody></table></div>; }
function Profile({ data }: any) { return <div className="profile-grid"><div><span>Customer ID</span><b>{data.external_id}</b></div><div><span>Country</span><b>{data.country || "—"}</b></div><div><span>Customer group</span><Badge value={data.segment}/></div><div><span>Likelihood of not returning</span><b>{pct(data.risk ?? data.churn_risk)}</b></div><div><span>Total recorded spend</span><b>{money(data.lifetime_value)}</b></div><div><span>Most recent purchase</span><b>{data.last_purchase_at ? new Date(data.last_purchase_at).toLocaleDateString() : "—"}</b></div></div>; }
function Metric({ label, value, note, tone }: any) { return <article className={`metric ${tone}`}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>; }
function Quick({ title, text, prompt, execute }: any) { return <button className="quick-card" onClick={() => execute(prompt)}><span>✦</span><div><b>{title}</b><p>{text}</p></div><i>→</i></button>; }
function Risk({ value }: any) { return <div className="risk"><span><i style={{ width: `${Math.round(value * 100)}%` }}></i></span><b>{pct(value)}</b></div>; }
const friendlySegment = (value: string) => ({ at_risk_high_value: "High-value customer at risk", active: "Standard customer", champion: "High-value loyal customer" }[String(value)] || String(value || "").replaceAll("_", " "));
function Badge({ value }: { value: string }) { return <span className={`badge ${String(value).replaceAll("_", "-")}`}>{friendlySegment(value)}</span>; }
function Nav({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: string; children: ReactNode }) { return <button className={active ? "active" : ""} onClick={onClick}><span>{icon}</span>{children}</button>; }
function Card({ title, eyebrow, action, children }: { title: string; eyebrow?: string; action?: ReactNode; children: ReactNode }) { return <section className="card"><div className="card-head"><div>{eyebrow && <p className="kicker">{eyebrow}</p>}<h2>{title}</h2></div>{action}</div>{children}</section>; }

createRoot(document.getElementById("root")!).render(<App/>);
