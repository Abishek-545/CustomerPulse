import { useEffect, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

declare global {
  interface Window { __CUSTOMERPULSE_CONFIG__?: { API_URL?: string } }
}
const API = window.__CUSTOMERPULSE_CONFIG__?.API_URL || import.meta.env.VITE_API_URL || "http://localhost:8000";
type Dashboard = { customers: number; products: number; orders: number; high_risk_customers: number; pending_approvals: number };
const request = (path: string, options?: RequestInit) => fetch(`${API}${path}`, options).then(async r => { if (!r.ok) throw new Error(await r.text()); return r.json(); });

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
    } catch (e) { setError("Could not reach the API. Start Docker Compose, then refresh."); }
  };
  useEffect(() => { refresh(); }, []);
  const investigate = async () => { setBusy(true); try { await request("/api/investigations", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({goal})}); await refresh(); } catch { setError("Investigation failed."); } finally { setBusy(false); } };
  const decide = async (id: number, approved: boolean) => { await request(`/api/approvals/${id}/decision`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({approved, decided_by:"dashboard-manager"})}); refresh(); };
  return <main>
    <header><div><p className="eyebrow">MCP-NATIVE AGENT OPERATIONS</p><h1>CustomerPulse</h1><p>Autonomous customer, product, and retention operations—with a human in control.</p></div><button onClick={refresh}>Refresh data</button></header>
    {error && <p className="error">{error}</p>}
    <section className="metrics">{dashboard && <>
      <Metric label="Customers" value={dashboard.customers}/><Metric label="Products" value={dashboard.products}/><Metric label="Orders" value={dashboard.orders}/><Metric label="High churn risk" value={dashboard.high_risk_customers}/><Metric label="Pending approvals" value={dashboard.pending_approvals}/>
    </>}</section>
    <section className="card agent"><h2>Start an agent investigation</h2><textarea value={goal} onChange={e=>setGoal(e.target.value)} /><button className="primary" disabled={busy} onClick={investigate}>{busy ? "Investigating…" : "Run autonomous investigation"}</button><p>The agent plans, queries customer/product data, checks memory, creates a draft only when justified, and requests approval.</p></section>
    <section className="grid"><Panel title="Investigation timeline"><ol>{investigations.map(i=><li key={i.id}><b>#{i.id} · {i.status}</b><br/>{i.goal}<br/><span>{(i.plan || []).join(" → ")}</span>{(i.findings || []).map((f:string, n:number)=><small key={n}>{f}</small>)}</li>)}</ol></Panel>
      <Panel title="Human approvals">{approvals.length ? approvals.map(a=><article className="approval" key={a.id}><b>Campaign #{a.campaign_id} · {a.status}</b><p>{a.reason}</p>{a.status === "pending" && <><button className="primary" onClick={()=>decide(a.id,true)}>Approve</button><button onClick={()=>decide(a.id,false)}>Reject</button></>}</article>) : <p>No actions awaiting approval.</p>}</Panel></section>
    <section className="grid"><Panel title="High-risk customers"><table><thead><tr><th>ID</th><th>Segment</th><th>Risk</th><th>LTV</th></tr></thead><tbody>{customers.map(c=><tr key={c.id}><td>{c.external_id}</td><td>{c.segment}</td><td>{Math.round(c.churn_risk*100)}%</td><td>£{c.lifetime_value}</td></tr>)}</tbody></table></Panel>
      <Panel title="Product risk signals"><table><thead><tr><th>Product</th><th>Cancellations</th><th>Trend</th></tr></thead><tbody>{products.map(p=><tr key={p.id}><td>{p.name}</td><td>{Math.round(p.cancellation_rate*100)}%</td><td className={p.sales_trend < 0 ? "bad" : "good"}>{Math.round(p.sales_trend*100)}%</td></tr>)}</tbody></table></Panel></section>
    <Panel title="MCP tool audit trail"><div className="audit">{audits.map(a=><div key={a.id}><b>{a.tool}</b><span>{JSON.stringify(a.output)}</span></div>)}</div></Panel>
  </main>;
}
function Metric({label, value}:{label:string; value:number}) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div>; }
function Panel({title, children}:{title:string; children:ReactNode}) { return <section className="card"><h2>{title}</h2>{children}</section>; }
createRoot(document.getElementById("root")!).render(<App/>);
