import { useEffect, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

declare global { interface Window { __CUSTOMERPULSE_CONFIG__?: { API_URL?: string } } }
const API = window.__CUSTOMERPULSE_CONFIG__?.API_URL || import.meta.env.VITE_API_URL || "http://localhost:8000";
type Dashboard = { customers: number; products: number; orders: number; high_risk_customers: number; pending_approvals: number };
const request = (path: string, options?: RequestInit) => fetch(`${API}${path}`, options).then(async response => { if (!response.ok) throw new Error(await response.text()); return response.json(); });

function App() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [customers, setCustomers] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [investigations, setInvestigations] = useState<any[]>([]);
  const [approvals, setApprovals] = useState<any[]>([]);
  const [audits, setAudits] = useState<any[]>([]);
  const [goal, setGoal] = useState("Find high-value customers likely to churn and create a safe retention plan.");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const refresh = async () => {
    try {
      const [d, c, p, i, a, logs] = await Promise.all([request("/api/dashboard"), request("/api/customers"), request("/api/products"), request("/api/investigations"), request("/api/approvals"), request("/api/audit-events")]);
      setDashboard(d); setCustomers(c); setProducts(p); setInvestigations(i); setApprovals(a); setAudits(logs); setError("");
    } catch { setError("Could not reach the live API. Check the backend service and CORS configuration, then refresh."); }
  };
  useEffect(() => { refresh(); }, []);
  const investigate = async () => { setBusy(true); try { await request("/api/investigations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ goal }) }); await refresh(); } catch { setError("Investigation failed."); } finally { setBusy(false); } };
  const decide = async (id: number, approved: boolean) => { try { await request(`/api/approvals/${id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approved, decided_by: "dashboard-manager" }) }); await refresh(); } catch { setError("Could not save the approval decision. Refresh and try again."); } };
  return <main>
    <header><div><p className="eyebrow">MCP-NATIVE AGENT OPERATIONS</p><h1>CustomerPulse</h1><p>Autonomous customer, product, and retention operations—with a human in control.</p></div><button onClick={refresh}>Refresh data</button></header>
    {error && <p className="error">{error}</p>}
    <section className="metrics">{dashboard && <><Metric label="Customers" value={dashboard.customers}/><Metric label="Products" value={dashboard.products}/><Metric label="Orders" value={dashboard.orders}/><Metric label="High churn risk" value={dashboard.high_risk_customers}/><Metric label="Pending approvals" value={dashboard.pending_approvals}/></>}</section>
    <section className="card agent"><h2>Start an agent investigation</h2><textarea value={goal} onChange={event => setGoal(event.target.value)} /><button className="primary" disabled={busy} onClick={investigate}>{busy ? "Investigating…" : "Run autonomous investigation"}</button><p>The agent plans, queries customer/product data, checks memory, creates a draft only when justified, and requests approval.</p></section>
    <section className="grid"><Panel title="Investigation timeline"><ol>{investigations.map(item => <li key={item.id}><b>#{item.id} · {item.status}</b><br/>{item.goal}<br/><span>{(item.plan || []).join(" → ")}</span>{(item.findings || []).map((finding: string, index: number) => <small key={index}>{finding}</small>)}</li>)}</ol></Panel><Panel title="Human approvals">{approvals.length ? approvals.map(approval => <article className="approval" key={approval.id}><b>Campaign #{approval.campaign_id} · {approval.status}</b><p>{approval.reason}</p><small>{approval.campaign_name} — {approval.campaign_offer}</small>{approval.status !== "pending" && <p className="outcome">Campaign is <b>{approval.campaign_status}</b> in the database. {approval.campaign_status === "active" ? "It is approved for activation; no real customer email or discount is sent by this demo." : "This campaign was not activated."}</p>}{approval.status === "pending" && <><button className="primary" onClick={() => decide(approval.id, true)}>Approve</button><button onClick={() => decide(approval.id, false)}>Reject</button></>}</article>) : <p>No actions awaiting approval.</p>}</Panel></section>
    <section className="grid"><Panel title="High-risk customers" className="scroll-panel"><div className="table-scroll"><table><thead><tr><th>ID</th><th>Segment</th><th>Risk</th><th>LTV</th></tr></thead><tbody>{customers.map(customer => <tr key={customer.id}><td>{customer.external_id}</td><td>{customer.segment}</td><td>{Math.round(customer.churn_risk * 100)}%</td><td>£{customer.lifetime_value}</td></tr>)}</tbody></table></div></Panel><Panel title="Product risk signals" className="scroll-panel"><div className="table-scroll"><table><thead><tr><th>Product</th><th>Cancellations</th><th>Trend</th></tr></thead><tbody>{products.map(product => <tr key={product.id}><td>{product.name}</td><td>{Math.round(product.cancellation_rate * 100)}%</td><td className={product.sales_trend < 0 ? "bad" : "good"}>{Math.round(product.sales_trend * 100)}%</td></tr>)}</tbody></table></div></Panel></section>
    <Panel title="MCP tool audit trail"><div className="audit">{audits.map(audit => <div key={audit.id}><b>{audit.tool}</b><span>{JSON.stringify(audit.output)}</span></div>)}</div></Panel>
  </main>;
}
function Metric({ label, value }: { label: string; value: number }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div>; }
function Panel({ title, children, className = "" }: { title: string; children: ReactNode; className?: string }) { return <section className={`card ${className}`}><h2>{title}</h2>{children}</section>; }
createRoot(document.getElementById("root")!).render(<App/>);
