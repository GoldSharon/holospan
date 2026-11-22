import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Blocks,
  Braces,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Database,
  FileSearch,
  Gauge,
  KeyRound,
  LockKeyhole,
  LogOut,
  Network,
  Orbit,
  PanelLeft,
  Settings2,
  ShieldCheck,
  Sparkles,
  Waypoints,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import {
  ApiError,
  fetchCapabilities,
  fetchOidcConfig,
  fetchSession,
  logout,
  type Membership,
} from './api'

const navigation = [
  { label: 'Overview', icon: Gauge, active: true },
  { label: 'Systems', icon: Blocks },
  { label: 'Assurance plans', icon: Waypoints },
  { label: 'Runs', icon: Activity },
  { label: 'Traces', icon: Network },
  { label: 'Evaluators', icon: Braces },
  { label: 'Evidence', icon: FileSearch },
]

const assuranceAreas = [
  { label: 'Task success', value: 'Not measured', accent: 'text-amber-200' },
  { label: 'Grounding', value: 'Not measured', accent: 'text-cyan-200' },
  { label: 'Tool safety', value: 'Policy ready', accent: 'text-emerald-200' },
]

function initials(name?: string | null, email?: string | null) {
  const source = name?.trim() || email?.split('@')[0] || 'Holospan user'
  return source
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')
}

function AccessScreen({ configured, unavailable }: { configured: boolean; unavailable?: boolean }) {
  return (
    <main className="access-shell">
      <section className="access-card" aria-labelledby="access-title">
        <div className="brand-mark access-mark" aria-hidden="true"><Orbit size={25} /></div>
        <p className="eyebrow"><ShieldCheck size={14} aria-hidden="true" /> Protected assurance workspace</p>
        <h1 id="access-title">{configured ? 'Sign in to Holospan.' : 'Connect your identity provider.'}</h1>
        <p className="access-copy">
          {configured
            ? 'Holospan uses your organization’s identity provider. Credentials and identity tokens stay outside browser storage.'
            : 'Identity is intentionally fail-closed. Configure the tenant OIDC issuer and client before opening customer evidence.'}
        </p>
        {configured ? (
          <a className="primary-button access-action" href="/api/v1/identity-access/login">
            <KeyRound size={17} aria-hidden="true" />
            Continue with organization SSO
            <ArrowRight size={17} aria-hidden="true" />
          </a>
        ) : (
          <div className="configuration-callout" role="status">
            <Settings2 size={18} aria-hidden="true" />
            <div>
              <strong>{unavailable ? 'Identity service unavailable' : 'OIDC configuration required'}</strong>
              <span>Set the pinned deployment’s HOLOSPAN_OIDC_* values, then restart the backend.</span>
            </div>
          </div>
        )}
        <p className="access-footnote">Opaque HttpOnly sessions · PKCE · CSRF protection · deny by default</p>
      </section>
    </main>
  )
}

function WorkspaceSwitcher({
  memberships,
  selectedTenantId,
  onSelect,
}: {
  memberships: Membership[]
  selectedTenantId?: string
  onSelect: (tenantId: string) => void
}) {
  const selected = memberships.find((membership) => membership.tenantId === selectedTenantId)
  if (memberships.length === 0) {
    return (
      <div className="workspace-switcher workspace-switcher-empty">
        <span className="avatar">--</span>
        <span className="workspace-copy"><strong>No workspace</strong><small>Ask a tenant administrator</small></span>
      </div>
    )
  }

  return (
    <label className="workspace-switcher" htmlFor="workspace-select">
      <span className="avatar">{initials(selected?.tenantName)}</span>
      <span className="workspace-copy">
        <strong>{selected?.tenantName ?? 'Select workspace'}</strong>
        <small>{selected?.roles.join(' · ') || 'Member'}</small>
      </span>
      <select id="workspace-select" aria-label="Current workspace" value={selectedTenantId} onChange={(event) => onSelect(event.target.value)}>
        {memberships.map((membership) => <option key={membership.id} value={membership.tenantId}>{membership.tenantName}</option>)}
      </select>
    </label>
  )
}

function Dashboard() {
  const queryClient = useQueryClient()
  const session = useQuery({ queryKey: ['identity-session'], queryFn: ({ signal }) => fetchSession(signal), retry: false })
  const [selectedTenantId, setSelectedTenantId] = useState<string>()
  const memberships = useMemo(() => session.data?.data.memberships ?? [], [session.data])
  const activeTenantId = useMemo(() => selectedTenantId ?? memberships[0]?.tenantId, [memberships, selectedTenantId])
  const capabilities = useQuery({
    queryKey: ['system-capabilities', activeTenantId],
    queryFn: ({ signal }) => fetchCapabilities(signal, activeTenantId),
    enabled: session.isSuccess,
    retry: false,
  })
  const signOut = useMutation({
    mutationFn: async () => logout(session.data?.data.csrfToken ?? ''),
    onSuccess: () => {
      queryClient.clear()
      window.location.assign('/')
    },
  })

  if (session.isPending) {
    return <main className="access-shell"><p className="loading-state" role="status">Verifying secure session…</p></main>
  }

  if (session.isError) {
    const error = session.error
    if (error instanceof ApiError && error.code === 'IDENTITY_NOT_CONFIGURED') return <AccessScreen configured={false} />
    return <AccessScreen configured={true} unavailable={error instanceof ApiError && error.status >= 500} />
  }

  const identity = session.data.data.principal
  const availableCount = capabilities.data?.data.capabilities.filter((capability) => capability.status === 'available').length

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand-lockup"><div className="brand-mark" aria-hidden="true"><Orbit size={21} /></div><div><p className="brand-name">Holospan</p><p className="brand-subtitle">AI Assurance</p></div></div>
        <nav className="nav-list">
          {navigation.map(({ label, icon: Icon, active }) => <button className={`nav-item ${active ? 'nav-item-active' : ''}`} key={label} type="button"><Icon aria-hidden="true" size={17} /><span>{label}</span></button>)}
        </nav>
        <div className="sidebar-card"><div className="sidebar-card-icon"><ShieldCheck size={16} /></div><p className="sidebar-card-title">Assurance state</p><p className="sidebar-card-copy">No claims are promoted without traceable evidence.</p></div>
        <WorkspaceSwitcher memberships={memberships} selectedTenantId={activeTenantId} onSelect={setSelectedTenantId} />
      </aside>

      <section className="workspace">
        <header className="topbar">
          <button className="icon-button mobile-menu" type="button" aria-label="Open navigation"><PanelLeft size={19} /></button>
          <div className="environment-pill"><CircleDot size={14} aria-hidden="true" />EC2 · Docker Compose</div>
          <div className="topbar-actions">
            <span className={`api-state ${capabilities.isError ? 'api-state-error' : ''}`}><span className="status-dot" aria-hidden="true" />{capabilities.isPending && 'Connecting'}{capabilities.isSuccess && 'API connected'}{capabilities.isError && 'API unavailable'}</span>
            <span className="signed-in-user" title={identity.email ?? undefined}><span className="avatar">{initials(identity.displayName, identity.email)}</span><span>{identity.displayName || identity.email || 'Signed in'}</span></span>
            <button className="secondary-button" type="button" disabled={signOut.isPending} onClick={() => signOut.mutate()}><LogOut size={15} aria-hidden="true" />{signOut.isPending ? 'Signing out…' : 'Sign out'}</button>
          </div>
        </header>

        <main id="main-content" className="main-content">
          <section className="hero" aria-labelledby="page-title">
            <div><p className="eyebrow"><Sparkles size={14} aria-hidden="true" /> Assurance workspace</p><h1 id="page-title">Prove what your agents can safely do.</h1><p className="hero-copy">Connect context, endpoints, and traces. Holospan turns them into reviewable scenarios, evaluations, and evidence-backed release decisions.</p></div>
            <button className="primary-button" type="button">Create a system<ArrowUpRight size={17} aria-hidden="true" /></button>
          </section>

          {memberships.length === 0 && <section className="empty-workspace-banner" role="status"><LockKeyhole size={19} aria-hidden="true" /><div><strong>Your identity is verified, but no tenant membership is active.</strong><span>Ask a tenant administrator to add this principal before accessing customer data.</span></div></section>}

          <section className="metrics-grid" aria-label="Workspace summary">
            <article className="metric-card metric-card-highlight"><div className="metric-icon"><Database size={18} /></div><p>Connected systems</p><strong>0</strong><span>Add source code, context, an endpoint, or traces.</span></article>
            <article className="metric-card"><div className="metric-icon"><Activity size={18} /></div><p>Assurance runs</p><strong>0</strong><span>No test or evaluation runs yet.</span></article>
            <article className="metric-card"><div className="metric-icon"><ShieldCheck size={18} /></div><p>Open findings</p><strong>0</strong><span>Findings appear with evidence and ownership.</span></article>
            <article className="metric-card"><div className="metric-icon"><Braces size={18} /></div><p>Available capabilities</p><strong>{availableCount ?? '—'}</strong><span>Reported by the protected backend contract.</span></article>
          </section>

          <section className="content-grid">
            <article className="panel getting-started">
              <div className="panel-heading"><div><p className="panel-kicker">First assurance loop</p><h2>Start with the evidence you already have</h2></div><span className="step-counter">0 / 4</span></div>
              <ol className="step-list">
                <li><span className="step-number">01</span><div><strong>Describe the system</strong><p>Upload a PRD, API contract, code, media, or policy.</p></div><ChevronRight size={17} /></li>
                <li><span className="step-number">02</span><div><strong>Connect its behavior</strong><p>Add an endpoint, OTLP stream, OpenInference, or trace export.</p></div><ChevronRight size={17} /></li>
                <li><span className="step-number">03</span><div><strong>Review the assurance plan</strong><p>Confirm risks, scenarios, evaluators, effects, and human gates.</p></div><ChevronRight size={17} /></li>
                <li><span className="step-number">04</span><div><strong>Run and decide</strong><p>Receive Pass, Fail, or Unable to Verify with exact evidence.</p></div><ChevronRight size={17} /></li>
              </ol>
            </article>
            <div className="right-column">
              <article className="panel"><div className="panel-heading compact"><div><p className="panel-kicker">Assurance coverage</p><h2>Quality signals</h2></div><CheckCircle2 className="muted-icon" size={20} /></div><div className="signal-list">{assuranceAreas.map((area) => <div className="signal-row" key={area.label}><span>{area.label}</span><strong className={area.accent}>{area.value}</strong></div>)}</div></article>
              <article className="panel architecture-panel"><div className="panel-heading compact"><div><p className="panel-kicker">Runtime</p><h2>Validation topology</h2></div></div><div className="topology-line" aria-label="Frontend connects to API, PostgreSQL and evidence services"><span>React</span><i /><span>FastAPI</span><i /><span>Evidence</span></div><p>One EC2 failure domain today. Portable contracts preserve the path to full AWS.</p></article>
            </div>
          </section>
        </main>
      </section>
    </div>
  )
}

function App() {
  const oidc = useQuery({ queryKey: ['oidc-config'], queryFn: ({ signal }) => fetchOidcConfig(signal), retry: false })
  if (oidc.isPending) return <main className="access-shell"><p className="loading-state" role="status">Loading secure workspace…</p></main>
  if (oidc.isError) return <AccessScreen configured={false} unavailable />
  if (!oidc.data.data.enabled) return <AccessScreen configured={false} />
  return <Dashboard />
}

export default App
