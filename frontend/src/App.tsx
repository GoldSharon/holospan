import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  ArrowUpRight,
  Blocks,
  Braces,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Database,
  FileSearch,
  Gauge,
  LockKeyhole,
  Network,
  Orbit,
  PanelLeft,
  ShieldCheck,
  Sparkles,
  Waypoints,
} from 'lucide-react'
import { fetchCapabilities } from './api'

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

function App() {
  const capabilities = useQuery({
    queryKey: ['system-capabilities'],
    queryFn: ({ signal }) => fetchCapabilities(signal),
  })

  const availableCount = capabilities.data?.data.capabilities.filter(
    (capability) => capability.status === 'available',
  ).length

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>

      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true"><Orbit size={21} /></div>
          <div>
            <p className="brand-name">Holospan</p>
            <p className="brand-subtitle">AI Assurance</p>
          </div>
        </div>

        <nav className="nav-list">
          {navigation.map(({ label, icon: Icon, active }) => (
            <button className={`nav-item ${active ? 'nav-item-active' : ''}`} key={label} type="button">
              <Icon aria-hidden="true" size={17} />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-card">
          <div className="sidebar-card-icon"><ShieldCheck size={16} /></div>
          <p className="sidebar-card-title">Assurance state</p>
          <p className="sidebar-card-copy">No claims are promoted without traceable evidence.</p>
        </div>

        <button className="workspace-switcher" type="button" aria-label="Open workspace switcher">
          <span className="avatar">HS</span>
          <span className="workspace-copy">
            <strong>Holospan Lab</strong>
            <small>EC2 validation</small>
          </span>
          <ChevronRight size={16} aria-hidden="true" />
        </button>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <button className="icon-button mobile-menu" type="button" aria-label="Open navigation">
            <PanelLeft size={19} />
          </button>
          <div className="environment-pill">
            <CircleDot size={14} aria-hidden="true" />
            EC2 · Docker Compose
          </div>
          <div className="topbar-actions">
            <span className={`api-state ${capabilities.isError ? 'api-state-error' : ''}`}>
              <span className="status-dot" aria-hidden="true" />
              {capabilities.isPending && 'Connecting'}
              {capabilities.isSuccess && 'API connected'}
              {capabilities.isError && 'API unavailable'}
            </span>
            <button className="secondary-button" type="button">
              <LockKeyhole size={15} aria-hidden="true" />
              Admin
            </button>
          </div>
        </header>

        <main id="main-content" className="main-content">
          <section className="hero" aria-labelledby="page-title">
            <div>
              <p className="eyebrow"><Sparkles size={14} aria-hidden="true" /> Assurance workspace</p>
              <h1 id="page-title">Prove what your agents can safely do.</h1>
              <p className="hero-copy">
                Connect context, endpoints, and traces. Holospan turns them into reviewable scenarios,
                evaluations, and evidence-backed release decisions.
              </p>
            </div>
            <button className="primary-button" type="button">
              Create a system
              <ArrowUpRight size={17} aria-hidden="true" />
            </button>
          </section>

          <section className="metrics-grid" aria-label="Workspace summary">
            <article className="metric-card metric-card-highlight">
              <div className="metric-icon"><Database size={18} /></div>
              <p>Connected systems</p>
              <strong>0</strong>
              <span>Add source code, context, an endpoint, or traces.</span>
            </article>
            <article className="metric-card">
              <div className="metric-icon"><Activity size={18} /></div>
              <p>Assurance runs</p>
              <strong>0</strong>
              <span>No test or evaluation runs yet.</span>
            </article>
            <article className="metric-card">
              <div className="metric-icon"><ShieldCheck size={18} /></div>
              <p>Open findings</p>
              <strong>0</strong>
              <span>Findings appear with evidence and ownership.</span>
            </article>
            <article className="metric-card">
              <div className="metric-icon"><Braces size={18} /></div>
              <p>Available capabilities</p>
              <strong>{availableCount ?? '—'}</strong>
              <span>Reported by the versioned backend contract.</span>
            </article>
          </section>

          <section className="content-grid">
            <article className="panel getting-started">
              <div className="panel-heading">
                <div>
                  <p className="panel-kicker">First assurance loop</p>
                  <h2>Start with the evidence you already have</h2>
                </div>
                <span className="step-counter">0 / 4</span>
              </div>

              <ol className="step-list">
                <li>
                  <span className="step-number">01</span>
                  <div><strong>Describe the system</strong><p>Upload a PRD, API contract, code, media, or policy.</p></div>
                  <ChevronRight size={17} />
                </li>
                <li>
                  <span className="step-number">02</span>
                  <div><strong>Connect its behavior</strong><p>Add an endpoint, OTLP stream, OpenInference, or trace export.</p></div>
                  <ChevronRight size={17} />
                </li>
                <li>
                  <span className="step-number">03</span>
                  <div><strong>Review the assurance plan</strong><p>Confirm risks, scenarios, evaluators, effects, and human gates.</p></div>
                  <ChevronRight size={17} />
                </li>
                <li>
                  <span className="step-number">04</span>
                  <div><strong>Run and decide</strong><p>Receive Pass, Fail, or Unable to Verify with exact evidence.</p></div>
                  <ChevronRight size={17} />
                </li>
              </ol>
            </article>

            <div className="right-column">
              <article className="panel">
                <div className="panel-heading compact">
                  <div><p className="panel-kicker">Assurance coverage</p><h2>Quality signals</h2></div>
                  <CheckCircle2 className="muted-icon" size={20} />
                </div>
                <div className="signal-list">
                  {assuranceAreas.map((area) => (
                    <div className="signal-row" key={area.label}>
                      <span>{area.label}</span>
                      <strong className={area.accent}>{area.value}</strong>
                    </div>
                  ))}
                </div>
              </article>

              <article className="panel architecture-panel">
                <div className="panel-heading compact">
                  <div><p className="panel-kicker">Runtime</p><h2>Validation topology</h2></div>
                </div>
                <div className="topology-line" aria-label="Frontend connects to API, PostgreSQL and evidence services">
                  <span>React</span><i /><span>FastAPI</span><i /><span>Evidence</span>
                </div>
                <p>One EC2 failure domain today. Portable contracts preserve the path to full AWS.</p>
              </article>
            </div>
          </section>
        </main>
      </section>
    </div>
  )
}

export default App
