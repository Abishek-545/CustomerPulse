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
const riskScore = (value: number) => `${Math.round((value || 0) * 100)}/100`;
const maskEmail = (value?: string) => {
  if (!value || !value.includes("@")) return "—";
  const [local, domain] = value.split("@");
  if (local.length <= 4) return `${local.slice(0, 1)}***@${domain}`;
  return `${local.slice(0, 3)}***${local.slice(-2)}@${domain}`;
};
type Tab = "overview" | "workspace" | "customers" | "campaigns" | "operations" | "quality" | "guide" | "audit";

function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [dashboard, setDashboard] = useState<any>(null);
  const [customers, setCustomers] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [investigations, setInvestigations] = useState<any[]>([]);
  const [approvals, setApprovals] = useState<any[]>([]);
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [audits, setAudits] = useState<any[]>([]);
  const [tasks, setTasks] = useState<any[]>([]);
  const [evaluations, setEvaluations] = useState<any[]>([]);
  const [mcpCapabilities, setMcpCapabilities] = useState<any>({});
  const [targets, setTargets] = useState<Record<number, any[]>>({});
  const [expandedCampaign, setExpandedCampaign] = useState<number | null>(null);
  const [query, setQuery] = useState("Show top 5 customers by lifetime value");
  const [agentResult, setAgentResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [managerNotice, setManagerNotice] = useState("");
  const [approvalBusy, setApprovalBusy] = useState<number | null>(null);

  useEffect(() => {
    if (!managerNotice) return;
    const timer = window.setTimeout(() => setManagerNotice(""), 5000);
    return () => window.clearTimeout(timer);
  }, [managerNotice]);

  useEffect(() => {
    if (!error) return;
    const timer = window.setTimeout(() => setError(""), 8000);
    return () => window.clearTimeout(timer);
  }, [error]);

  const refresh = async () => {
    try {
      const [summary, customerRows, productRows, runs, gates, campaignRows, logs, taskRows, evaluationRows, capabilities] = await Promise.all([
        call("/api/dashboard"), call("/api/customers?limit=100"), call("/api/products"), call("/api/investigations"),
        call("/api/approvals"), call("/api/campaigns"), call("/api/audit-events"), call("/api/operational-tasks").catch(() => []), call("/api/evaluations").catch(() => []), call("/api/mcp/capabilities").catch(() => ({})),
      ]);
      setDashboard(summary); setCustomers(customerRows); setProducts(productRows); setInvestigations(runs);
      setApprovals(gates); setCampaigns(campaignRows); setAudits(logs); setTasks(taskRows); setEvaluations(evaluationRows); setMcpCapabilities(capabilities); setError("");
    } catch (cause) {
      const detail = cause instanceof Error ? cause.message : "Unknown connection error";
      setError(`The live API is unavailable: ${detail}`);
    }
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
    if (approvalBusy !== null) return;
    setApprovalBusy(id); setError("");
    try {
      const result = await call(`/api/approvals/${id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approved, decided_by: "dashboard-manager" }) });
      setManagerNotice(result.email_delivery?.manager_notification || `Campaign ${result.campaign_status}.`);
      await refresh();
    } catch (cause) {
      try {
        const latest = await call("/api/approvals");
        const saved = latest.find((item: any) => item.id === id && item.status !== "pending");
        if (saved) {
          setManagerNotice(`Campaign #${saved.campaign_id} was successfully ${saved.status}. The dashboard recovered after a response interruption.`);
          await refresh();
        } else {
          setError(cause instanceof Error ? `Approval failed: ${cause.message}` : "The approval could not be saved.");
        }
      } catch {
        setError("The approval result could not be confirmed. Refresh before trying again.");
      }
    } finally { setApprovalBusy(null); }
  };
  const simulateOutcome = async (campaignId: number) => { try { const result = await call(`/api/campaigns/${campaignId}/simulate-outcome`, { method: "POST" }); setManagerNotice(`Campaign #${campaignId} completed: ${result.converted} conversions, ${pct(result.uplift)} uplift, ${money(result.attributed_revenue)} attributed revenue.`); await refresh(); } catch (cause) { setError(cause instanceof Error ? cause.message : "Outcome processing failed."); } };
  const retryDelivery = async (campaignId: number) => { try { const result = await call(`/api/campaigns/${campaignId}/deliver`, { method: "POST" }); setManagerNotice(result.manager_notification); await refresh(); } catch (cause) { setError(cause instanceof Error ? cause.message : "Email delivery retry failed."); } };
  const updateTaskStatus = async (taskId: string, status: "open" | "completed") => { try { await call(`/api/operational-tasks/${taskId}/status`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) }); setManagerNotice(`${taskId} marked ${status}.`); await refresh(); } catch (cause) { setError(cause instanceof Error ? cause.message : "The work item could not be updated."); } };
  const runEvaluations = async () => { try { setManagerNotice("Evaluation suite is running…"); const result = await call("/api/evaluations/run", { method: "POST" }); await refresh(); setEvaluations(previous => [result, ...previous.filter(item => item.id !== result.id)]); setManagerNotice(`Evaluation complete: ${result.scores.passed}/${result.scores.cases} cases passed.`); } catch { setError("The evaluation suite could not run."); } };
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
        <Nav active={tab === "operations"} onClick={() => setTab("operations")} icon="✓">Operations</Nav>
        <Nav active={tab === "quality"} onClick={() => setTab("quality")} icon="◎">Quality & MCP</Nav>
        <Nav active={tab === "guide"} onClick={() => setTab("guide")} icon="?">How it works</Nav>
        <Nav active={tab === "audit"} onClick={() => setTab("audit")} icon="≡">Audit trail</Nav>
      </nav>
      <div className="system-status"><i></i><div><strong>System operational</strong><span>Groq · LangGraph · MCP</span></div></div>
    </aside>
    <main className="content">
      <header className="topbar"><div><p className="kicker">CUSTOMER INTELLIGENCE PLATFORM</p><h1>{tab === "overview" ? "Operations overview" : tab === "workspace" ? "Multi-agent workspace" : tab === "guide" ? "How CustomerPulse works" : tab[0].toUpperCase() + tab.slice(1)}</h1></div><button className="secondary" onClick={refresh}>↻ Refresh</button></header>
      {error && <div className="alert" role="alert"><b>Action needed</b><span>{error}</span><button aria-label="Close error notification" onClick={() => setError("")}>×</button></div>}
      {managerNotice && <div className="manager-notice" role="status"><b>Manager notification</b><span>{managerNotice}</span><button aria-label="Close manager notification" onClick={() => setManagerNotice("")}>×</button></div>}
      {tab === "overview" && <Overview dashboard={dashboard} investigations={investigations} campaigns={campaigns} pending={pending} products={products} execute={execute} />}
      {tab === "workspace" && <Workspace query={query} setQuery={setQuery} clearResult={() => setAgentResult(null)} execute={execute} busy={busy} response={agentResult} investigations={investigations} openCampaigns={() => setTab("campaigns")} openOperations={() => setTab("operations")} />}
      {tab === "customers" && <Customers rows={filteredCustomers} search={search} setSearch={setSearch} execute={execute} />}
      {tab === "campaigns" && <Campaigns dashboard={dashboard} campaigns={campaigns} approvals={approvals} targets={targets} expanded={expandedCampaign} toggle={toggleTargets} decide={decide} approvalBusy={approvalBusy} simulateOutcome={simulateOutcome} retryDelivery={retryDelivery} />}
      {tab === "operations" && <Operations tasks={tasks} execute={execute} updateTaskStatus={updateTaskStatus}/>}
      {tab === "quality" && <Quality evaluations={evaluations} capabilities={mcpCapabilities} runEvaluations={runEvaluations}/>}
      {tab === "guide" && <Guide execute={execute}/>}
      {tab === "audit" && <Audit rows={audits} />}
    </main>
  </div>;
}

function Overview({ dashboard, investigations, campaigns, pending, products, execute }: any) {
  return <>
    <section className="intro-card"><div><p className="kicker">WHAT THIS APP DOES</p><h2>Turn retail order history into explainable customer and product actions</h2><p>CustomerPulse explores customers, spending, cancellations, and product signals; creates traceable internal care or recovery work; and prepares customer emails only through a manager-approved campaign.</p></div><button className="secondary" onClick={() => execute("Explain what this app does and the role of each agent")}>Ask how it works →</button></section>
    <section className="metrics-row">
      <Metric label="Customer records" value={dashboard?.customers ?? "—"} note="Profiles stored in PostgreSQL" tone="blue"/>
      <Metric label="Invoices" value={dashboard?.orders ?? "—"} note="Unique purchase invoices" tone="violet"/>
      <Metric label="Higher inactivity risk" value={dashboard?.high_risk_customers ?? "—"} note="Relative risk score ≥ 65" tone="amber"/>
      <Metric label="Eligible for retention" value={dashboard?.eligible_retention_customers ?? "—"} note="High-value, high-risk, not targeted" tone="violet"/>
      <Metric label="Pending approvals" value={dashboard?.pending_approvals ?? "—"} note="Human decision required" tone="green"/>
    </section>
    <section className="quick-section"><div className="section-heading"><div><p className="kicker">QUICK ACTIONS</p><h2>Ask the specialist agents</h2></div><span>Read-only requests never create campaigns</span></div>
      <div className="quick-grid">
        <Quick title="Top customers" text="Rank customers by lifetime purchase value." prompt="Show top 5 customers by lifetime value" execute={execute}/>
        <Quick title="Customer profile" text="Inspect risk, segment, country and value." prompt="Show customer 16244 details" execute={execute}/>
        <Quick title="Purchase history" text="Retrieve recent invoices for one customer." prompt="Show purchase history for customer 16244" execute={execute}/>
        <Quick title="Churn analysis (read-only)" text="Investigate risk evidence without creating a campaign." prompt="Analyze the top 10 customers at churn risk" execute={execute}/>
        <Quick title="Support triage" text="Create deduplicated Customer Care work records; no email is sent." prompt="Create support cases for 10 risky customers" execute={execute}/>
        <Quick title="Product recovery" text="Create internal product investigation tasks; product data is not changed." prompt="Create product recovery tasks for 5 products" execute={execute}/>
        <Quick title="Cancellation feedback" text="Find repeat cancellers and prepare a manager-approved feedback email." prompt="Create a feedback email campaign for 10 customers with cancelled orders" execute={execute}/>
        <Quick title="Product portfolio" text="Compare low-price cancellation problems with reliable high-price products." prompt="Show 10 low-value products with most cancellations and high-value products with least cancellations" execute={execute}/>
        <Quick title="Explain CustomerPulse" text="Learn the metrics, agents, and safety rules." prompt="What does this app do, what do its metrics mean, and what is the role of each agent?" execute={execute}/>
      </div>
    </section>
    <section className="two-col">
      <Card title="Recent agent runs" eyebrow="LANGGRAPH EXECUTIONS"><RunList rows={investigations.slice(0, 6)}/></Card>
      <Card title="Retention capacity" eyebrow="HUMAN-IN-THE-LOOP"><div className="campaign-summary"><strong>{dashboard?.eligible_retention_customers ?? "—"}</strong><span>customers still eligible</span><strong>{dashboard?.currently_targeted_customers ?? "—"}</strong><span>retention customers targeted</span></div><p className="muted">Duplicate protection is scoped by purpose. A customer cannot receive the same retention or feedback campaign repeatedly, but a retention action does not incorrectly block a later, distinct feedback request.</p></Card>
    </section>
  </>;
}

function Workspace({ query, setQuery, clearResult, execute, busy, response, investigations, openCampaigns, openOperations }: any) {
  const examples = ["What does this app do?", "Explain churn risk, lifetime value, and customer segments", "Show top 5 customers by lifetime value", "Show customers whose lifetime value is over 5000", "Show customers in France", "Show 10 customers with most cancelled orders", "Create a feedback email campaign for 10 customers with cancelled orders", "Show low-value products with most cancellations and high-value products with least cancellations", "Create a retention campaign for 10 high-value customers", "Create support cases for 10 risky customers", "Create product recovery tasks for 5 products", "Show operational tasks"];
  return <>
    <section className="command-card"><div className="command-title"><div className="agent-orb">✦</div><div><h2>Ask CustomerPulse</h2><p>Supervisor routes your request to the correct specialist agents.</p></div></div>
      <div className="command-box"><textarea value={query} onChange={event => { setQuery(event.target.value); clearResult(); }} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); execute(); } }} placeholder="Ask what the app does, what a metric means, or ask about customers, purchases, risk and campaigns…"/><button disabled={busy} onClick={() => execute()}>{busy ? "Agents working…" : "Run request →"}</button></div>
      <div className="chips">{examples.map(item => <button key={item} onClick={() => execute(item)}>{item}</button>)}</div>
    </section>
    {busy && <section className="working"><i></i><div><b>Multi-agent workflow is running</b><span>Supervisor → Customer Intelligence → Product Intelligence → Memory → Response</span></div></section>}
    {response && !busy && <Result response={response} execute={execute} openCampaigns={openCampaigns} openOperations={openOperations}/>}
    <Card title="Execution history" eyebrow="OBSERVABLE AGENT RUNS"><RunList rows={investigations.slice(0, 10)}/></Card>
  </>;
}

function Result({ response, execute, openCampaigns, openOperations }: any) {
  const result = response.result || {}; const data = result.data || {};
  const customers = data.customers || [];
  return <section className="result-card"><div className="result-head"><div><span className="status-dot"></span><b>Request completed</b><p>{result.summary}</p></div><Badge value={response.intent || result.kind}/></div>
    {result.agents && <div className="agent-chain">{result.agents.map((agent: string, index: number) => <span key={agent}>{agent}{index < result.agents.length - 1 && <i>→</i>}</span>)}</div>}
    {result.decision_log && <div className="decision-log"><b>Autonomous decisions</b>{result.decision_log.map((item: any, index: number) => <p key={index}><span>{item.decision}</span>{item.rationale}</p>)}</div>}
    {customers.length > 0 && <CustomerTable rows={customers}/>}
    {result.kind === "product_portfolio" && <ProductPortfolio data={data}/>}
    {result.kind === "customer_detail" && <Profile data={data}/>}
    {result.kind === "purchase_history" && <><Profile data={data.customer}/><OrderTable rows={data.orders || []}/></>}
    {result.kind === "help" && <HelpResult data={data}/>}
    {result.kind === "churn_analysis" && <div className="result-cta"><div><b>Analysis only—no customer action was created.</b><p>Create a separate campaign draft if you want these findings to reach the manager approval queue.</p></div><button className="approve" onClick={() => execute("Create a retention campaign for 10 high-value customers")}>Create campaign draft →</button></div>}
    {result.kind === "campaign" && <div className="campaign-result"><strong>{result.created ? result.target_count : 0}</strong><span>{result.created ? "unique customers selected" : "campaigns created"}</span>{result.created ? <><b>{result.excluded_existing_targets} duplicate targets excluded</b><p>Campaign #{result.campaign_id} is a draft awaiting human approval.</p><button className="approve result-action" onClick={openCampaigns}>Open approval queue →</button></> : <p>No eligible customer remains; nobody was retargeted.</p>}</div>}
    {(result.kind === "support_triage" || result.kind === "product_recovery") && <div className="action-result"><strong>{data.created_count || 0}</strong><span>{result.kind === "support_triage" ? "new support cases created" : "new product recovery tasks created"}</span><p>{data.existing_count ? `${data.existing_count} matching open records already existed and were not duplicated.` : data.created_count ? "Every created record is visible in Operations." : "No unhandled qualifying records remained, so no duplicate work was created."}</p><button className="secondary result-action" onClick={openOperations}>Open Operations backlog →</button></div>}
    {result.kind === "operational_tasks" && <TaskList rows={data.tasks || []}/>}
    {result.kind === "campaign_outcome" && <Outcome data={data}/>}
  </section>;
}

function Customers({ rows, search, setSearch, execute }: any) {
  return <Card title="Customer health and value" eyebrow="LIVE POSTGRESQL DATA" action={<input className="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search customer ID, country, or group…"/>}>
    <p className="table-explainer">The risk score ranks customers relative to this dataset: 75% comes from recency rank and 25% from completed-order-frequency rank. It is deliberately distributed across 5–95 and is not a literal churn probability. Spending is a separate dimension.</p>
    <div className="table-wrap"><table><thead><tr><th>Customer ID</th><th>Country</th><th>Customer group</th><th title="Relative inactivity ranking based on recency and completed-order frequency">Inactivity risk score</th><th title="Total net amount this customer spent in the imported purchase history">Total customer spend</th><th></th></tr></thead><tbody>{rows.map((item: any) => <tr key={item.id}><td><b>{item.external_id}</b></td><td>{item.country}</td><td><Badge value={item.segment}/></td><td><Risk value={item.churn_risk}/></td><td><b>{money(item.lifetime_value)}</b></td><td><button className="link" onClick={() => execute(`Show customer ${item.external_id} details`)}>View profile →</button></td></tr>)}</tbody></table></div>
  </Card>;
}

function Campaigns({ dashboard, campaigns, approvals, targets, expanded, toggle, decide, approvalBusy, simulateOutcome, retryDelivery }: any) {
  const approvalFor = (id: number) => approvals.find((item: any) => item.campaign_id === id);
  return <div className="campaign-list"><section className="capacity-card"><div><span>Retention customers remaining</span><strong>{dashboard?.eligible_retention_customers ?? "—"}</strong></div><div><span>Retention customers targeted</span><strong>{dashboard?.currently_targeted_customers ?? "—"}</strong></div><p>Duplicate protection is scoped by campaign purpose: retention customers are not repeatedly targeted, and frequent cancellers are not repeatedly asked for feedback.</p></section>{campaigns.length === 0 && <Card title="No campaigns yet"><p className="muted">Explicitly request a campaign from the Agent workspace.</p></Card>}{campaigns.map((campaign: any) => { const approval = approvalFor(campaign.id); const rows = targets[campaign.id] || []; const delivered = (campaign.delivery?.sent || 0) + (campaign.delivery?.simulated || 0); return <section className="campaign-card" key={campaign.id}>
    <div className="campaign-main"><div><div className="campaign-title"><span>Campaign #{campaign.id}</span><StatusBadge value={campaign.status}/></div><h2>{campaign.name}</h2><p>{campaign.offer} · Customer group: {friendlySegment(campaign.segment)}</p></div><div className="target-total"><strong>{campaign.target_count}</strong><span>target customers</span></div></div>
    {campaign.status !== "draft" && campaign.status !== "rejected" && <div className="delivery-strip"><b>Email delivery</b><span>{campaign.delivery?.sent || 0} sent</span><span>{campaign.delivery?.simulated || 0} simulated</span><span className={campaign.delivery?.failed ? "danger" : ""}>{campaign.delivery?.failed || 0} failed</span>{delivered === 0 && <span className="danger">No delivery recorded</span>}</div>}
    {campaign.outcome && <Outcome data={campaign.outcome} legacy={campaign.outcome.delivered === 0}/>}
    <div className="campaign-actions"><button className="secondary" onClick={() => toggle(campaign.id)}>{expanded === campaign.id ? "Hide customers" : `View ${campaign.target_count} customers`}</button>{approval?.status === "pending" && <><button className="approve" disabled={approvalBusy !== null} onClick={() => decide(approval.id, true)}>{approvalBusy === approval.id ? "Saving approval…" : "Approve & send emails"}</button><button className="reject" disabled={approvalBusy !== null} onClick={() => decide(approval.id, false)}>Reject</button></>} {campaign.status === "active" && (delivered === 0 || campaign.delivery?.failed > 0) && <button className="secondary" onClick={() => retryDelivery(campaign.id)}>Retry email delivery</button>} {campaign.status === "active" && delivered > 0 && <button className="approve" onClick={() => simulateOutcome(campaign.id)}>Complete & measure outcome</button>} {approval && approval.status !== "pending" && <span className="decision">Decision: <b>{approval.status}</b>{approval.decided_by ? ` by ${approval.decided_by}` : ""}</span>}</div>
    {expanded === campaign.id && <div className="target-panel">{campaign.target_count === 0 ? <p className="muted">Legacy segment-level campaign: no individual targets were recorded.</p> : rows.length === 0 ? <p className="muted">Loading targets…</p> : <CustomerTable rows={rows}/>}</div>}
  </section>; })}</div>;
}

function Operations({ tasks, execute, updateTaskStatus }: any) {
  const supportTasks = tasks.filter((item: any) => item.type === "support_followup");
  const productTasks = tasks.filter((item: any) => item.type === "product_recovery");
  return <div className="operations-page">
  <section className="ops-hero"><div><p className="kicker">MORE THAN DISCOUNTS</p><h2>Autonomous customer and product operations</h2><p>These workflows create real, deduplicated PostgreSQL work records. They do not contact customers: a team member completes each backlog item, while email workflows always use the manager approval queue.</p></div></section>
  <section className="operation-purpose-grid"><article><h3>Support triage</h3><p>Finds high-inactivity-risk customers without an open case and creates one internal follow-up case per customer for the Customer Care team.</p><button onClick={() => execute("Create support cases for 10 risky customers")}>Create support cases</button></article><article><h3>Product recovery</h3><p>Finds products with high cancellation rates and creates one investigation task per product for quality, description, pricing, or fulfillment review.</p><button onClick={() => execute("Create product recovery tasks for 5 products")}>Create recovery tasks</button></article><article><h3>Cancellation feedback</h3><p>Ranks repeat cancellers from order history, drafts a feedback campaign, and pauses before email delivery until a manager approves it.</p><button onClick={() => execute("Create a feedback email campaign for 10 customers with cancelled orders")}>Prepare feedback outreach</button></article></section>
  <div className="operations-queues">
    <Card title={`Customer Care cases (${supportTasks.length})`} eyebrow="SUPPORT_CASES TABLE"><p className="table-explainer">One internal follow-up record per qualifying customer. Completing a case updates its PostgreSQL status; it does not send an email.</p><TaskList rows={supportTasks} onStatus={updateTaskStatus} empty="No Customer Care cases yet."/></Card>
    <Card title={`Product recovery tasks (${productTasks.length})`} eyebrow="OPERATIONAL_TASKS TABLE"><p className="table-explainer">One internal investigation per product cancellation signal. Completing a task records that the operational review is done; it does not edit the product.</p><TaskList rows={productTasks} onStatus={updateTaskStatus} empty="No product recovery tasks yet."/></Card>
  </div>
</div>; }

function Quality({ evaluations, capabilities, runEvaluations }: any) {
  const latest = evaluations[0]; const servers = Object.entries(capabilities || {});
  return <div className="quality-page">
    <section className="quality-hero"><div><p className="kicker">CONTINUOUS QUALITY</p><h2>Agent evaluation and real MCP capability discovery</h2><p>This is a deterministic regression suite for 48 curated prompts: routing, parameter extraction, unsafe-action prevention, and allowed trajectories. A 100% result means the current code passed those known cases—not that the AI is 100% accurate on unseen requests. MCP cards come from live protocol discovery.</p></div><button onClick={runEvaluations}>Run evaluation suite →</button></section>
    {latest ? <section className="score-grid"><Score label="Intent accuracy" value={latest.scores.intent_accuracy}/><Score label="Parameter accuracy" value={latest.scores.parameter_accuracy}/><Score label="Unsafe-action prevention" value={latest.scores.unsafe_action_prevention}/><Score label="Trajectory validity" value={latest.scores.trajectory_validity}/><article><span>Cases passed</span><strong>{latest.scores.passed}/{latest.scores.cases}</strong></article></section> : <Card title="No evaluation run yet"><p className="muted">Run the versioned regression suite to create a measurable quality baseline.</p></Card>}
    <section className="mcp-grid">{servers.map(([name, value]: any) => <article key={name}><div><b>{name} MCP server</b><Badge value={value.transport}/></div><p>{value.tools?.length || 0} tools · {value.resources?.length || 0} resources · {value.prompts?.length || 0} prompts</p><small>{(value.tools || []).join(" · ")}</small></article>)}</section>
    {latest && <Card title={`All ${latest.scores.cases} evaluated prompts`} eyebrow="DETERMINISTIC TRAJECTORY REGRESSION"><div className="eval-cases">{latest.details.map((item: any) => <article key={item.prompt}><span className={item.intent_ok && item.parameter_ok && item.safety_ok && item.trajectory_ok ? "pass" : "fail"}></span><div><b>{item.prompt}</b><small>{item.actual_intent} · {(item.actions || []).join(" → ")}</small></div></article>)}</div></Card>}
  </div>;
}

function TaskList({ rows, onStatus, empty = "No operational tasks yet." }: any) { return <div className="task-list">{rows.length === 0 && <p className="muted">{empty}</p>}{rows.map((item: any) => <article key={item.id}><div><Badge value={item.priority}/><b>{item.title}</b></div><p>{item.description}</p><div className="task-footer"><span>#{item.id} · {item.status}</span>{onStatus && <button className="secondary task-status" onClick={() => onStatus(item.id, item.status === "completed" ? "open" : "completed")}>{item.status === "completed" ? "Reopen" : "Mark completed"}</button>}</div></article>)}</div>; }
function Outcome({ data, legacy = false }: any) { if (legacy) return <div className="legacy-outcome"><b>No delivery evidence for this legacy campaign</b><span>The earlier demo run recorded an outcome before email delivery was enforced. New campaigns cannot be completed until at least one email is sent or simulated.</span></div>; return <div className="outcome-strip"><div><span>Delivered</span><b>{data.delivered || 0}</b></div><div><span>Opened</span><b>{data.opened || 0}</b></div><div><span>Clicked</span><b>{data.clicked || 0}</b></div><div><span>Converted</span><b>{data.converted || 0}</b></div><div><span>Uplift</span><b>{pct(data.uplift)}</b></div><div><span>Revenue</span><b>{money(data.revenue ?? data.attributed_revenue)}</b></div></div>; }
function Score({ label, value }: any) { return <article><span>{label}</span><strong>{pct(value)}</strong><i style={{width:pct(value)}}></i></article>; }

function Guide({ execute }: any) {
  const agents = [
    ["Supervisor & Planner", "Understands the goal, creates a constrained plan, and chooses the smallest set of specialists."],
    ["Customer Intelligence", "Queries customer profiles, purchases, locations, spend, and inactivity risk through MCP tools."],
    ["Customer Order", "Aggregates completed and cancelled invoices per customer, ranks repeat cancellers, and supplies evidence for feedback outreach."],
    ["Product Intelligence", "Checks product returns, cancellations, and demand signals when they are relevant."],
    ["Product Portfolio", "Compares lower-price cancellation problems with higher-price products that have low cancellation rates."],
    ["Memory", "Retrieves prior campaign outcomes and stores useful lessons for later runs."],
    ["Campaign & Safety", "Selects unique eligible customers, creates a draft, and pauses for human approval."],
    ["Customer Care", "Creates deduplicated internal support cases when the user explicitly requests proactive triage."],
    ["Product Operations", "Creates recovery tasks for products whose cancellation evidence justifies action."],
    ["Observer & Replanner", "Checks every tool result, removes unjustified dependent actions, and enforces the step limit."],
    ["Response & Learning", "Combines evidence into one result and writes completed campaign outcomes into memory."],
  ];
  return <div className="guide-page">
    <section className="guide-hero"><p className="kicker">PLAIN-ENGLISH PRODUCT GUIDE</p><h2>CustomerPulse finds retention opportunities without silently acting on customers</h2><p>It analyzes real PostgreSQL customer and invoice records, lets specialist agents answer operational questions, and creates customer-specific retention drafts only when you explicitly request a campaign.</p><button onClick={() => execute("Explain what this app does, its metrics, campaign rules, and every agent role")}>Ask the agents to explain it →</button></section>
    <section><div className="section-heading"><div><p className="kicker">METRIC DEFINITIONS</p><h2>What the customer columns mean</h2></div></div><div className="definition-grid">
      <Definition title="Total customer spend" technical="Lifetime value (LTV)" text="The customer's total net spend in the imported transaction history. Example: £1,056 means the recorded purchases minus cancellations total £1,056."/>
      <Definition title="Relative risk of not returning" technical="Inactivity risk score" text="A 5–95 relative ranking: 75% recency percentile plus 25% completed-order-frequency percentile. It compares customers within this dataset; it is not a predicted probability."/>
      <Definition title="Customer group" technical="Segment" text="A clear combination of two independent facts: relative inactivity risk is high at 65/100 or above, and spend is high at £250 or above. Profiles with no linked orders are clearly marked as insufficient history instead of being called active."/>
    </div></section>
    <section className="card"><div className="card-head"><div><p className="kicker">AUTONOMOUS MULTI-AGENT ARCHITECTURE</p><h2>Plan → execute → observe → replan</h2></div></div><p className="table-explainer">Each specialist owns a narrow responsibility and MCP tool set. The LangGraph planner creates a goal-specific plan, agents share evidence through durable PostgreSQL graph state, and the observer decides after every tool result whether to continue, revise, or stop.</p><div className="agent-role-list">{agents.map(([name, text]) => <article key={name}><b>{name}</b><p>{text}</p></article>)}</div></section>
    <section className="policy-note"><b>What happens when campaign customers run out?</b><p>Every campaign permanently records its exact customer IDs, so a later campaign cannot target them again under this demo policy. With a static dataset, the eligible count eventually reaches zero and no campaign is created. New transaction data or an explicitly approved re-engagement policy can replenish the pool.</p></section>
  </div>;
}

function Definition({ title, technical, text }: any) { return <article className="definition-card"><span>{technical}</span><h3>{title}</h3><p>{text}</p></article>; }
function HelpResult({ data }: any) { return <div className="help-result"><div className="help-answer"><h3>CustomerPulse explained</h3><p>{data.answer}</p></div><div className="definition-grid">{(data.definitions || []).map((item: any) => <Definition key={item.term} title={item.plain_name} technical={item.term} text={`${item.meaning} ${item.example || ""}`}/>)}</div><div className="agent-role-list">{(data.agents || []).map((item: any) => <article key={item.name}><b>{item.name}</b><p>{item.role}</p></article>)}</div>{data.campaign_policy && <div className="policy-note"><b>Campaign safety and capacity</b><p>{data.campaign_policy}</p></div>}</div>; }

function Audit({ rows }: any) { return <Card title="MCP tool audit trail" eyebrow="TRACEABLE AGENT ACTIONS"><div className="audit-list">{rows.map((item: any) => <article key={item.id}><div><span className="tool-icon">M</span><b>{item.tool}</b></div><time>{new Date(item.created_at).toLocaleString()}</time><code>{JSON.stringify(item.output)}</code></article>)}</div></Card>; }
function RunList({ rows }: any) { return <div className="run-list">{rows.length === 0 && <p className="muted">No agent runs yet.</p>}{rows.map((item: any) => <article key={item.id}><span className={`run-status ${item.status}`}></span><div><b>#{item.id} · {item.goal}</b><small>{(item.plan || []).join(" → ")}</small></div><Badge value={item.status}/></article>)}</div>; }
function CustomerTable({ rows }: any) { if (rows.some((item: any) => item.cancelled_orders !== undefined)) return <CancellationTable rows={rows}/>; return <div className="table-wrap result-table"><table className="customer-result-table"><thead><tr><th scope="col">Customer ID</th><th scope="col">Country</th><th scope="col">Customer group</th><th scope="col">Inactivity risk score</th><th scope="col">Total customer spend</th></tr></thead><tbody>{rows.map((item: any) => <tr key={item.id || item.customer_id}><td><b>{item.external_id}</b></td><td>{item.country || "—"}</td><td>{item.segment ? friendlySegment(item.segment) : "—"}</td><td className="numeric">{riskScore(item.risk ?? item.churn_risk)}</td><td className="numeric"><b>{money(item.lifetime_value ?? item.ltv)}</b></td></tr>)}</tbody></table></div>; }
function CancellationTable({ rows }: any) { return <div className="table-wrap result-table"><table><thead><tr><th>Customer ID</th><th>Country</th><th>Cancelled orders</th><th>Total orders</th><th>Cancellation rate</th><th>Cancelled value</th></tr></thead><tbody>{rows.map((item: any) => <tr key={item.id}><td><b>{item.external_id}</b></td><td>{item.country || "—"}</td><td>{item.cancelled_orders}</td><td>{item.total_orders}</td><td>{pct(item.cancellation_rate)}</td><td>{money(item.cancelled_value)}</td></tr>)}</tbody></table></div>; }
function ProductPortfolio({ data }: any) { const PortfolioTable = ({ rows }: any) => <div className="table-wrap result-table"><table><thead><tr><th>Product</th><th>SKU</th><th>Unit price</th><th>Cancellation rate</th><th>Sales trend</th></tr></thead><tbody>{rows.map((p: any) => <tr key={p.id}><td><b>{p.name}</b></td><td>{p.sku}</td><td>{money(p.unit_price)}</td><td>{pct(p.cancellation_rate)}</td><td>{pct(p.sales_trend)}</td></tr>)}</tbody></table></div>; return <div className="portfolio-result"><p>{data.method} Median price: <b>{money(data.price_split)}</b>.</p><h3>Lower-price products with the most cancellations</h3><PortfolioTable rows={data.most_cancelled_low_value || []}/><h3>Higher-price products with the fewest cancellations</h3><PortfolioTable rows={data.high_value_low_cancellation || []}/></div>; }
function OrderTable({ rows }: any) { return <div className="table-wrap result-table"><table><thead><tr><th>Invoice</th><th>Date</th><th>Status</th><th>Total</th></tr></thead><tbody>{rows.map((item: any) => <tr key={item.invoice}><td><b>{item.invoice}</b></td><td>{new Date(item.date).toLocaleDateString()}</td><td><Badge value={item.status}/></td><td>{money(item.total)}</td></tr>)}</tbody></table></div>; }
function Profile({ data }: any) { return <div className="profile-grid"><div><span>Customer ID</span><b>{data.external_id}</b></div><div><span>Email recipient</span><b>{maskEmail(data.email)}</b></div><div><span>Country</span><b>{data.country || "—"}</b></div><div><span>Customer group</span><Badge value={data.segment}/></div><div><span>Inactivity risk score</span><b>{riskScore(data.risk ?? data.churn_risk)}</b></div><div><span>Total recorded spend</span><b>{money(data.lifetime_value)}</b></div><div><span>Most recent purchase</span><b>{data.last_purchase_at ? new Date(data.last_purchase_at).toLocaleDateString() : "—"}</b></div></div>; }
function Metric({ label, value, note, tone }: any) { return <article className={`metric ${tone}`}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>; }
function Quick({ title, text, prompt, execute }: any) { return <button className="quick-card" onClick={() => execute(prompt)}><span>✦</span><div><b>{title}</b><p>{text}</p></div><i>→</i></button>; }
function Risk({ value }: any) { return <div className="risk"><span><i style={{ width: `${Math.round(value * 100)}%` }}></i></span><b>{riskScore(value)}</b></div>; }
const friendlySegment = (value: string) => ({ at_risk_high_value: "High-spend customer at risk", at_risk_lower_value: "Lower-spend customer at risk", high_value_active: "High-spend active customer", regular_active: "Lower-spend active customer", insufficient_history: "Insufficient order history", active: "Legacy active customer", champion: "Legacy high-value customer", frequent_cancellers: "Frequent order cancellers" }[String(value)] || String(value || "").replaceAll("_", " "));
function Badge({ value }: { value: string }) { return <span className={`badge ${String(value).replaceAll("_", "-")}`}>{friendlySegment(value)}</span>; }
function StatusBadge({ value }: { value: string }) { return <span className={`badge ${String(value).replaceAll("_", "-")}`}>{String(value || "unknown").replaceAll("_", " ")}</span>; }
function Nav({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: string; children: ReactNode }) { return <button className={active ? "active" : ""} onClick={onClick}><span>{icon}</span>{children}</button>; }
function Card({ title, eyebrow, action, children }: { title: string; eyebrow?: string; action?: ReactNode; children: ReactNode }) { return <section className="card"><div className="card-head"><div>{eyebrow && <p className="kicker">{eyebrow}</p>}<h2>{title}</h2></div>{action}</div>{children}</section>; }

createRoot(document.getElementById("root")!).render(<App/>);
