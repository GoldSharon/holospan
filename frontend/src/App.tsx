import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  ArrowRight,
  Blocks,
  Braces,
  CheckCircle2,
  Database,
  FileSearch,
  Gauge,
  KeyRound,
  LockKeyhole,
  LogOut,
  Menu,
  Network,
  Orbit,
  Plus,
  Settings2,
  ShieldCheck,
  Sparkles,
  Waypoints,
  X,
} from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'
import {
  ApiError,
  createSystem,
  fetchCapabilities,
  fetchOidcConfig,
  fetchSession,
  fetchSystems,
  logout,
  type CreateSystemInput,
  type Membership,
} from './api'
import { CreateSystemDialog, SystemsWorkspace } from './SystemWorkspace'

const navigation = [
  { id: 'overview', label: 'Overview', icon: Gauge },
  { id: 'systems', label: 'Systems', icon: Blocks },
  { id: 'assurance-plans', label: 'Assurance plans', icon: Waypoints },
  { id: 'runs', label: 'Runs', icon: Activity },
  { id: 'traces', label: 'Traces', icon: Network },
  { id: 'evaluators', label: 'Evaluators', icon: Braces },
  { id: 'evidence', label: 'Evidence', icon: FileSearch },
] as const

type SectionId = (typeof navigation)[number]['id']

const plannedSections: Record<Exclude<SectionId, 'overview' | 'systems'>, { title: string; kicker: string; description: string; next: string }> = {
  'assurance-plans': {
    title: 'Assurance plans',
    kicker: 'Risk-based coverage',
    description: 'Define scenarios, evaluators, safety policies, and human decision gates for each system.',
    next: 'Create a system first. Plan generation will be added as a separate reviewed capability.',
  },
  runs: {
    title: 'Runs',
    kicker: 'Evaluation execution',
    description: 'Track pre-production tests and continuous production evaluations with reproducible evidence.',
    next: 'No runs exist yet. Execution will activate after assurance plans are available.',
  },
  traces: {
    title: 'Traces',
    kicker: 'Observed behavior',
    description: 'Investigate sessions, model calls, tools, retrieval, latency, tokens, cost, and agent trajectories.',
    next: 'Trace ingestion is not connected yet. OTLP and OpenInference setup will be implemented next.',
  },
  evaluators: {
    title: 'Evaluators',
    kicker: 'Quality measurement',
    description: 'Manage deterministic checks, code evaluators, LLM-as-judge, JEV-as-judge, and human review.',
    next: 'Evaluator configuration is planned and is not represented as active in this release.',
  },
  evidence: {
    title: 'Evidence',
    kicker: 'Assurance record',
    description: 'Review findings, decisions, audit history, and traceable proof behind every assurance claim.',
    next: 'Evidence will appear only after a verified run produces it.',
  },
}

const assuranceAreas = [
  { label: 'Task success', value: 'Not measured', className: 'signal-warning' },
  { label: 'Grounding', value: 'Not measured', className: 'signal-neutral' },
  { label: 'Tool safety', value: 'Policy ready', className: 'signal-ready' },
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
            ? 'Use your organization’s single sign-on to enter the assurance workspace.'
            : 'Identity is intentionally fail-closed. An administrator must configure organizational sign-on before customer evidence can be accessed.'}
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
              <strong>{unavailable ? 'Identity service unavailable' : 'Identity configuration required'}</strong>
              <span>Ask a platform administrator to complete the identity-provider setup.</span>
            </div>
          </div>
        )}
        <p className="access-footnote">Secure session · protected sign-in · tenant-isolated access</p>
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

function PlannedSection({ section }: { section: Exclude<SectionId, 'overview' | 'systems'> }) {
  const content = plannedSections[section]
  return (
    <section className="section-page" aria-labelledby={`${section}-title`}>
      <div className="section-header">
        <div>
          <p className="section-kicker">{content.kicker}</p>
          <h1 id={`${section}-title`}>{content.title}</h1>
          <p>{content.description}</p>
        </div>
      </div>
      <div className="empty-state">
        <LockKeyhole size={25} aria-hidden="true" />
        <h2>Not active yet</h2>
        <p>{content.next}</p>
      </div>
    </section>
  )
}

function Overview({
  systemCount,
  availableCount,
  canCreateSystem,
  onCreateSystem,
}: {
  systemCount: number | null
  availableCount?: number
  canCreateSystem: boolean
  onCreateSystem: (invoker: HTMLButtonElement) => void
}) {
  return (
    <>
      <section className="hero" aria-labelledby="page-title">
        <div>
          <p className="eyebrow"><Sparkles size={14} aria-hidden="true" /> Assurance workspace</p>
          <h1 id="page-title">Prove what your agents can safely do.</h1>
          <p className="hero-copy">Connect context, endpoints, and traces. Turn observed behavior into reviewable scenarios, evaluations, and evidence-backed release decisions.</p>
        </div>
        <button className="primary-button" type="button" disabled={!canCreateSystem} onClick={(event) => onCreateSystem(event.currentTarget)}>
          <Plus size={17} aria-hidden="true" />Create a system
        </button>
      </section>

      <section className="metrics-grid" aria-label="Workspace summary">
        <article className="metric-card metric-card-highlight"><div className="metric-icon"><Database size={18} /></div><p>Connected systems</p><strong>{systemCount ?? '—'}</strong><span>Systems with context, endpoint, code, or trace inputs.</span></article>
        <article className="metric-card"><div className="metric-icon"><Activity size={18} /></div><p>Assurance runs</p><strong>0</strong><span>No test or evaluation runs yet.</span></article>
        <article className="metric-card"><div className="metric-icon"><ShieldCheck size={18} /></div><p>Open findings</p><strong>0</strong><span>Findings will include evidence and ownership.</span></article>
        <article className="metric-card"><div className="metric-icon"><Braces size={18} /></div><p>Available capabilities</p><strong>{availableCount ?? '—'}</strong><span>Protected services ready for this workspace.</span></article>
      </section>

      <section className="content-grid">
        <article className="panel getting-started">
          <div className="panel-heading"><div><p className="panel-kicker">First assurance loop</p><h2>Start with the evidence you already have</h2></div><span className="step-counter">0 / 4</span></div>
          <ol className="step-list">
            <li><span className="step-number">01</span><div><strong>Describe the system</strong><p>Add a PRD, API contract, code, media, or policy after creating the system.</p></div><span className="step-state">Available</span></li>
            <li><span className="step-number">02</span><div><strong>Connect its behavior</strong><p>Add an endpoint, OTLP stream, OpenInference, or trace export.</p></div><span className="step-state">Planned</span></li>
            <li><span className="step-number">03</span><div><strong>Review the assurance plan</strong><p>Confirm risks, scenarios, evaluators, effects, and human gates.</p></div><span className="step-state">Planned</span></li>
            <li><span className="step-number">04</span><div><strong>Run and decide</strong><p>Receive Pass, Fail, or Unable to Verify with exact evidence.</p></div><span className="step-state">Planned</span></li>
          </ol>
        </article>
        <div className="right-column">
          <article className="panel"><div className="panel-heading compact"><div><p className="panel-kicker">Assurance coverage</p><h2>Quality signals</h2></div><CheckCircle2 className="muted-icon" size={20} /></div><div className="signal-list">{assuranceAreas.map((area) => <div className="signal-row" key={area.label}><span>{area.label}</span><strong className={area.className}>{area.value}</strong></div>)}</div></article>
          <article className="panel principle-panel"><div className="panel-heading compact"><div><p className="panel-kicker">Evidence rule</p><h2>Claims require proof</h2></div><ShieldCheck className="muted-icon" size={20} /></div><p>Holospan does not promote a quality or safety claim until it can link the decision to repeatable evaluation evidence.</p></article>
        </div>
      </section>
    </>
  )
}

function Dashboard() {
  const queryClient = useQueryClient()
  const session = useQuery({ queryKey: ['identity-session'], queryFn: ({ signal }) => fetchSession(signal), retry: false })
  const [selectedTenantId, setSelectedTenantId] = useState<string>()
  const [activeSection, setActiveSection] = useState<SectionId>('overview')
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const memberships = useMemo(() => session.data?.data.memberships ?? [], [session.data])
  const activeTenantId = useMemo(() => selectedTenantId ?? memberships[0]?.tenantId, [memberships, selectedTenantId])
  const activeMembership = memberships.find((membership) => membership.tenantId === activeTenantId)
  const canReadSystems = Boolean(activeMembership?.permissions.includes('system_context.systems.read'))
  const canManageSystems = Boolean(activeMembership?.permissions.includes('system_context.systems.manage'))
  const capabilities = useQuery({
    queryKey: ['system-capabilities', activeTenantId],
    queryFn: ({ signal }) => fetchCapabilities(signal, activeTenantId),
    enabled: session.isSuccess,
    retry: false,
  })
  const systems = useQuery({
    queryKey: ['systems', activeTenantId],
    queryFn: ({ signal }) => fetchSystems(activeTenantId, signal),
    enabled: session.isSuccess && Boolean(activeTenantId) && canReadSystems,
    retry: false,
  })
  const closeCreateDialog = useCallback(() => {
    setCreateDialogOpen(false)
    window.requestAnimationFrame(() => document.getElementById('create-system-action')?.focus())
  }, [])
  const openCreateDialog = useCallback(() => {
    if (!canManageSystems) return
    setActiveSection('systems')
    setMobileNavOpen(false)
    setCreateDialogOpen(true)
  }, [canManageSystems])
  const createSystemMutation = useMutation({
    mutationFn: (input: CreateSystemInput) => {
      if (!activeTenantId || !session.data?.data.csrfToken) throw new Error('No active workspace')
      return createSystem(activeTenantId, session.data.data.csrfToken, input)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['systems', activeTenantId] })
      closeCreateDialog()
    },
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
  const pageLabel = navigation.find((item) => item.id === activeSection)?.label ?? 'Overview'
  const selectSection = (section: SectionId) => {
    setActiveSection(section)
    setMobileNavOpen(false)
  }
  const changeTenant = (tenantId: string) => {
    setSelectedTenantId(tenantId)
    setCreateDialogOpen(false)
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      {mobileNavOpen && <button className="nav-scrim" type="button" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)} />}
      <aside className={`sidebar ${mobileNavOpen ? 'sidebar-open' : ''}`} aria-label="Primary navigation">
        <div className="brand-lockup"><div className="brand-mark" aria-hidden="true"><Orbit size={21} /></div><div><p className="brand-name">Holospan</p><p className="brand-subtitle">AI Assurance</p></div><button className="icon-button sidebar-close" type="button" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)}><X size={18} /></button></div>
        <nav className="nav-list">
          {navigation.map(({ id, label, icon: Icon }) => (
            <button
              className={`nav-item ${activeSection === id ? 'nav-item-active' : ''}`}
              key={id}
              type="button"
              aria-current={activeSection === id ? 'page' : undefined}
              onClick={() => selectSection(id)}
            >
              <Icon aria-hidden="true" size={17} /><span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-card"><div className="sidebar-card-icon"><ShieldCheck size={16} /></div><p className="sidebar-card-title">Evidence-first assurance</p><p className="sidebar-card-copy">No quality or safety claim is promoted without traceable proof.</p></div>
        <WorkspaceSwitcher memberships={memberships} selectedTenantId={activeTenantId} onSelect={changeTenant} />
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div className="topbar-context"><button className="icon-button mobile-menu" type="button" aria-label="Open navigation" aria-expanded={mobileNavOpen} onClick={() => setMobileNavOpen(true)}><Menu size={19} /></button><span>{pageLabel}</span></div>
          <div className="topbar-actions">
            <span className={`api-state ${capabilities.isError ? 'api-state-error' : ''}`}><span className="status-dot" aria-hidden="true" />{capabilities.isPending && 'Connecting'}{capabilities.isSuccess && 'Service available'}{capabilities.isError && 'Service unavailable'}</span>
            <span className="signed-in-user" title={identity.email ?? undefined}><span className="avatar">{initials(identity.displayName, identity.email)}</span><span>{identity.displayName || identity.email || 'Signed in'}</span></span>
            <button className="secondary-button" type="button" disabled={signOut.isPending} onClick={() => signOut.mutate()}><LogOut size={15} aria-hidden="true" />{signOut.isPending ? 'Signing out…' : 'Sign out'}</button>
          </div>
        </header>

        <main id="main-content" className="main-content">
          {memberships.length === 0 && <section className="empty-workspace-banner" role="status"><LockKeyhole size={19} aria-hidden="true" /><div><strong>Your identity is verified, but no workspace membership is active.</strong><span>Ask a tenant administrator to add this account before accessing customer data.</span></div></section>}

          {activeSection === 'overview' && (
            <Overview
              systemCount={canReadSystems && systems.isSuccess ? systems.data.data.items.length : memberships.length ? 0 : null}
              availableCount={availableCount}
              canCreateSystem={canManageSystems}
              onCreateSystem={openCreateDialog}
            />
          )}
          {activeSection === 'systems' && (
            <SystemsWorkspace
              systems={systems.data?.data.items ?? []}
              isPending={systems.isPending}
              isError={systems.isError}
              canRead={canReadSystems}
              canManage={canManageSystems}
              onRetry={() => { void systems.refetch() }}
              onOpenCreate={openCreateDialog}
            />
          )}
          {activeSection !== 'overview' && activeSection !== 'systems' && <PlannedSection section={activeSection} />}
        </main>
      </section>

      {createDialogOpen && (
        <CreateSystemDialog
          isPending={createSystemMutation.isPending}
          error={createSystemMutation.error}
          onClose={closeCreateDialog}
          onSubmit={(input) => createSystemMutation.mutate(input)}
        />
      )}
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
