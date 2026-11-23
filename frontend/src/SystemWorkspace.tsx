import {
  AlertCircle,
  ArrowLeft,
  Blocks,
  Bot,
  Braces,
  Check,
  CheckCircle2,
  Cloud,
  FileText,
  FileUp,
  GitBranch,
  Network,
  Plus,
  RadioTower,
  RotateCw,
  Search,
  ShieldCheck,
  Sparkles,
  Workflow,
  X,
  type LucideIcon,
} from 'lucide-react'
import { type FormEvent, type KeyboardEvent as ReactKeyboardEvent, useEffect, useRef, useState } from 'react'
import { ApiError, type CreateSystemInput, type SourceKind, type SourceSummary, type SystemSummary } from './api'

const systemTypeLabels: Record<SystemSummary['systemType'], string> = {
  agent: 'AI agent',
  rag: 'RAG application',
  workflow: 'AI workflow',
  model: 'Model service',
  api: 'AI-enabled API',
  other: 'Other system',
}

const lifecycleLabels: Record<SystemSummary['lifecycleStage'], string> = {
  development: 'Development',
  staging: 'Staging',
  production: 'Production',
}

const systemTypeOptions: Array<{
  value: SystemSummary['systemType']
  label: string
  description: string
  icon: LucideIcon
}> = [
  { value: 'agent', label: 'AI agent', description: 'Tool-using autonomous system', icon: Bot },
  { value: 'rag', label: 'RAG app', description: 'Retrieval-grounded experience', icon: Search },
  { value: 'workflow', label: 'AI workflow', description: 'Multi-step orchestration', icon: Workflow },
  { value: 'model', label: 'Model service', description: 'Hosted model or inference API', icon: Sparkles },
  { value: 'api', label: 'AI-enabled API', description: 'Product or service endpoint', icon: Braces },
  { value: 'other', label: 'Other', description: 'Custom AI-enabled system', icon: Blocks },
]

const lifecycleOptions: Array<{
  value: SystemSummary['lifecycleStage']
  label: string
  description: string
}> = [
  { value: 'development', label: 'Development', description: 'Actively being built' },
  { value: 'staging', label: 'Staging', description: 'Pre-production validation' },
  { value: 'production', label: 'Production', description: 'Serving live workloads' },
]

const sourcePreview: Array<{ label: string; detail: string; icon: LucideIcon }> = [
  { label: 'Code', detail: 'GitHub · Azure Repos', icon: GitBranch },
  { label: 'Context', detail: 'S3 · documents · media', icon: FileText },
  { label: 'Runtime', detail: 'Agent · API endpoint', icon: Network },
  { label: 'Telemetry', detail: 'OTLP · OpenInference', icon: RadioTower },
]

function toSlug(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 63)
}

export function CreateSystemDialog({
  isPending,
  error,
  onClose,
  onSubmit,
}: {
  isPending: boolean
  error: Error | null
  onClose: () => void
  onSubmit: (input: CreateSystemInput) => void
}) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const nameRef = useRef<HTMLInputElement>(null)
  const pendingRef = useRef(isPending)
  const [displayName, setDisplayName] = useState('')
  const [slug, setSlug] = useState('')
  const [slugEdited, setSlugEdited] = useState(false)
  const [description, setDescription] = useState('')
  const [systemType, setSystemType] = useState<SystemSummary['systemType']>('agent')
  const [lifecycleStage, setLifecycleStage] = useState<SystemSummary['lifecycleStage']>('development')

  useEffect(() => {
    pendingRef.current = isPending
  }, [isPending])

  useEffect(() => {
    const priorFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    nameRef.current?.focus()
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape' && !pendingRef.current) {
        event.preventDefault()
        onClose()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      priorFocus?.focus()
    }
  }, [onClose])

  const trapFocus = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Tab') return
    const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), summary',
    )
    if (!focusable?.length) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onSubmit({
      displayName,
      slug,
      description: description.trim() || null,
      systemType,
      lifecycleStage,
    })
  }

  const SelectedTypeIcon = systemTypeOptions.find((option) => option.value === systemType)?.icon ?? Bot

  return (
    <div className="dialog-backdrop" role="presentation">
      <div
        ref={dialogRef}
        className="dialog-card system-setup-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-system-title"
        aria-describedby="create-system-description"
        onKeyDown={trapFocus}
      >
        <header className="setup-header">
          <div className="setup-title-lockup">
            <span className="setup-title-icon"><ShieldCheck size={20} aria-hidden="true" /></span>
            <div>
              <h2 id="create-system-title">Create a system</h2>
              <p id="create-system-description">Add the basic system details. Connect code, context, endpoints, and telemetry next.</p>
            </div>
          </div>
          <button className="icon-button" type="button" aria-label="Close create system dialog" disabled={isPending} onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </header>

        <ol className="setup-progress" aria-label="System setup progress">
          <li className="setup-step setup-step-active"><span>1</span><div><strong>System profile</strong><small>Add system details</small></div></li>
          <li><span>2</span><div><strong>Connect sources</strong><small>Code, context and runtime</small></div></li>
          <li><span>3</span><div><strong>Assurance plan</strong><small>Review generated coverage</small></div></li>
        </ol>

        <form className="system-setup-form" onSubmit={submit}>
          <div className="system-setup-grid">
            <div className="setup-fields">
              <div className="field-heading">
                <div><span className="field-step">01</span><h3>Identify the system</h3></div>
                <p>Use a name your engineering, risk, and assurance teams already recognize.</p>
              </div>

              <label className="form-field">
                <span>System name</span>
                <input
                  ref={nameRef}
                  required
                  minLength={2}
                  maxLength={120}
                  autoComplete="off"
                  aria-label="System name"
                  placeholder="e.g. Claims Copilot"
                  value={displayName}
                  onChange={(event) => {
                    const nextName = event.target.value
                    setDisplayName(nextName)
                    if (!slugEdited) setSlug(toSlug(nextName))
                  }}
                />
                <small>Shown across projects, runs, findings, and evidence exports.</small>
              </label>

              <label className="form-field">
                <span>Description <em>Optional</em></span>
                <textarea
                  maxLength={2000}
                  rows={3}
                  placeholder="What does this system do, who uses it, and what decisions can it influence?"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                />
              </label>

              <fieldset className="choice-fieldset">
                <legend>System type</legend>
                <div className="system-type-grid">
                  {systemTypeOptions.map(({ value, label, description: optionDescription, icon: Icon }) => (
                    <label className={`type-choice ${systemType === value ? 'type-choice-selected' : ''}`} key={value}>
                      <input
                        type="radio"
                        name="systemType"
                        value={value}
                        checked={systemType === value}
                        onChange={() => setSystemType(value)}
                      />
                      <span className="choice-icon"><Icon size={17} aria-hidden="true" /></span>
                      <span className="choice-copy"><strong>{label}</strong><small>{optionDescription}</small></span>
                      <span className="choice-check" aria-hidden="true"><Check size={12} /></span>
                    </label>
                  ))}
                </div>
              </fieldset>

              <fieldset className="choice-fieldset">
                <legend>Lifecycle stage</legend>
                <div className="lifecycle-grid">
                  {lifecycleOptions.map(({ value, label, description: optionDescription }) => (
                    <label className={`lifecycle-choice ${lifecycleStage === value ? 'lifecycle-choice-selected' : ''}`} key={value}>
                      <input
                        type="radio"
                        name="lifecycleStage"
                        value={value}
                        checked={lifecycleStage === value}
                        onChange={() => setLifecycleStage(value)}
                      />
                      <strong>{label}</strong>
                      <small>{optionDescription}</small>
                    </label>
                  ))}
                </div>
              </fieldset>

              <details className="advanced-settings">
                <summary>Advanced identifier</summary>
                <label className="form-field">
                  <span>System slug</span>
                  <input
                    required
                    minLength={3}
                    maxLength={63}
                    pattern="[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])"
                    autoComplete="off"
                    aria-label="System slug"
                    value={slug}
                    onChange={(event) => {
                      setSlugEdited(true)
                      setSlug(toSlug(event.target.value))
                    }}
                  />
                  <small>Stable workspace identifier. Generated automatically from the system name.</small>
                </label>
              </details>
            </div>

            <aside className="setup-preview" aria-label="System setup summary">
              <div className="preview-label"><span>Setup preview</span><span className="draft-badge">Draft</span></div>
              <div className="system-preview-card">
                <span className="system-preview-icon"><SelectedTypeIcon size={21} aria-hidden="true" /></span>
                <div>
                  <strong>{displayName.trim() || 'Untitled system'}</strong>
                  <span>{systemTypeLabels[systemType]} · {lifecycleLabels[lifecycleStage]}</span>
                </div>
              </div>

              <div className="source-preview-heading">
                <div><Cloud size={16} aria-hidden="true" /><strong>Connect every source</strong></div>
                <p>Nothing is mutually exclusive. Add any combination after this profile is created.</p>
              </div>
              <ul className="source-preview-list">
                {sourcePreview.map(({ label, detail, icon: Icon }) => (
                  <li key={label}><span><Icon size={15} aria-hidden="true" /></span><div><strong>{label}</strong><small>{detail}</small></div><small className="source-state">Next</small></li>
                ))}
              </ul>

              <div className="assurance-note">
                <ShieldCheck size={16} aria-hidden="true" />
                <p><strong>Evidence stays attributable.</strong><span>Every future source is versioned and linked to the runs it informed.</span></p>
              </div>
            </aside>
          </div>

          {error && (
            <div className="form-error" role="alert">
              <AlertCircle size={17} aria-hidden="true" />
              <span>{error instanceof ApiError ? error.message : 'The system could not be created. Try again.'}</span>
            </div>
          )}

          <footer className="dialog-actions setup-actions">
            <p><ShieldCheck size={14} aria-hidden="true" />No credentials or customer data are required at this step.</p>
            <div>
              <button className="secondary-button" type="button" disabled={isPending} onClick={onClose}>Cancel</button>
              <button className="primary-button" type="submit" disabled={isPending || displayName.trim().length < 2 || slug.length < 3}>
                {isPending ? 'Creating…' : 'Create system'}
              </button>
            </div>
          </footer>
        </form>
      </div>
    </div>
  )
}

export function SystemsWorkspace({
  systems,
  isPending,
  isError,
  canRead,
  canManage,
  onRetry,
  onOpenCreate,
  onOpenSystem,
}: {
  systems: SystemSummary[]
  isPending: boolean
  isError: boolean
  canRead: boolean
  canManage: boolean
  onRetry: () => void
  onOpenCreate: (invoker: HTMLButtonElement) => void
  onOpenSystem: (systemId: string) => void
}) {
  return (
    <section className="section-page" aria-labelledby="systems-title">
      <div className="section-header">
        <div>
          <p className="section-kicker">System portfolio</p>
          <h1 id="systems-title">Systems</h1>
          <p>Define each AI system once, then attach context, behavior, assurance plans, and evidence over time.</p>
        </div>
        {canManage && (
          <button id="create-system-action" className="primary-button" type="button" onClick={(event) => onOpenCreate(event.currentTarget)}>
            <Plus size={17} aria-hidden="true" />Create system
          </button>
        )}
      </div>

      {!canRead && <div className="empty-state"><Blocks size={24} aria-hidden="true" /><h2>System access is not assigned</h2><p>Ask a workspace administrator for system read access.</p></div>}
      {canRead && isPending && <div className="empty-state" role="status"><p>Loading systems…</p></div>}
      {canRead && isError && (
        <div className="empty-state" role="alert">
          <AlertCircle size={24} aria-hidden="true" />
          <h2>Systems are temporarily unavailable</h2>
          <p>The workspace is still secure. Retry when the service is available.</p>
          <button className="secondary-button" type="button" onClick={onRetry}><RotateCw size={15} aria-hidden="true" />Retry</button>
        </div>
      )}
      {canRead && !isPending && !isError && systems.length === 0 && (
        <div className="empty-state">
          <Blocks size={25} aria-hidden="true" />
          <h2>No systems yet</h2>
          <p>Create the system you want to evaluate. Code, context, endpoints, and telemetry can all be connected next.</p>
        </div>
      )}
      {canRead && !isPending && !isError && systems.length > 0 && (
        <div className="system-grid" aria-label="Systems">
          {systems.map((system) => (
            <button
              className="system-card system-card-action"
              type="button"
              aria-label={`Open ${system.displayName}`}
              key={system.id}
              onClick={() => onOpenSystem(system.id)}
            >
              <div className="system-card-heading"><span className="system-icon"><Blocks size={18} aria-hidden="true" /></span><span className="status-badge">Draft</span></div>
              <h2>{system.displayName}</h2>
              <p>{system.description || 'No description added.'}</p>
              <dl>
                <div><dt>Type</dt><dd>{systemTypeLabels[system.systemType]}</dd></div>
                <div><dt>Stage</dt><dd>{lifecycleLabels[system.lifecycleStage]}</dd></div>
                <div><dt>Connections</dt><dd>Not connected</dd></div>
              </dl>
            </button>
          ))}
        </div>
      )}
    </section>
  )
}

const sourceKindLabels: Record<SourceKind, string> = {
  context_document: 'Context document',
  api_contract: 'API contract',
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  return `${(value / 1024).toFixed(value < 10 * 1024 ? 1 : 0)} KB`
}

export function SystemDetailWorkspace({
  system,
  sources,
  isSystemPending,
  isSystemError,
  isSourcesPending,
  isSourcesError,
  canReadSources,
  canManageSources,
  isUploadPending,
  uploadError,
  onBack,
  onRetrySystem,
  onRetrySources,
  onUpload,
}: {
  system?: SystemSummary
  sources: SourceSummary[]
  isSystemPending: boolean
  isSystemError: boolean
  isSourcesPending: boolean
  isSourcesError: boolean
  canReadSources: boolean
  canManageSources: boolean
  isUploadPending: boolean
  uploadError: Error | null
  onBack: () => void
  onRetrySystem: () => void
  onRetrySources: () => void
  onUpload: (kind: SourceKind, file: File) => Promise<void>
}) {
  const [kind, setKind] = useState<SourceKind>('context_document')
  const [file, setFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  if (isSystemPending) {
    return <section className="system-detail-page"><div className="empty-state" role="status">Loading system…</div></section>
  }
  if (isSystemError || !system) {
    return (
      <section className="system-detail-page">
        <button className="back-button" type="button" onClick={onBack}><ArrowLeft size={16} aria-hidden="true" />All systems</button>
        <div className="empty-state" role="alert"><AlertCircle size={24} aria-hidden="true" /><h1>System unavailable</h1><p>The workspace could not load this system.</p><button className="secondary-button" type="button" onClick={onRetrySystem}>Retry</button></div>
      </section>
    )
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!file) return
    try {
      await onUpload(kind, file)
      setFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch {
      // The mutation error is rendered without discarding the selected file.
    }
  }

  return (
    <section className="system-detail-page" aria-labelledby="system-detail-title">
      <button className="back-button" type="button" onClick={onBack}><ArrowLeft size={16} aria-hidden="true" />All systems</button>
      <header className="system-detail-header">
        <div>
          <div className="system-detail-meta"><span>{systemTypeLabels[system.systemType]}</span><span>{lifecycleLabels[system.lifecycleStage]}</span><span>Draft</span></div>
          <h1 id="system-detail-title">{system.displayName}</h1>
          <p>{system.description || 'No description has been added for this system.'}</p>
        </div>
        <div className="system-identity-card"><span>System ID</span><code>{system.slug}</code><small>Evidence and runs remain linked to this identity.</small></div>
      </header>

      <div className="source-section-heading">
        <div><p className="section-kicker">Source coverage</p><h2>Connect what you already have</h2><p>Sources are additive. Use any combination of context, code, runtime behavior, and telemetry.</p></div>
        <span className="source-count">{sources.length} connected</span>
      </div>

      <div className="source-category-grid" aria-label="Source categories">
        <article className="source-category source-category-planned"><span className="source-category-icon"><GitBranch size={18} aria-hidden="true" /></span><div><h3>Code repository</h3><p>GitHub and Azure Repos connections.</p></div><span className="planned-badge">Planned</span></article>
        <article className="source-category source-category-ready"><span className="source-category-icon"><FileText size={18} aria-hidden="true" /></span><div><h3>Context &amp; contracts</h3><p>Requirements, policies, and API specifications.</p></div><span className="available-badge">Available</span></article>
        <article className="source-category source-category-planned"><span className="source-category-icon"><Network size={18} aria-hidden="true" /></span><div><h3>Runtime endpoint</h3><p>Agent and API behavior connections.</p></div><span className="planned-badge">Planned</span></article>
        <article className="source-category source-category-planned"><span className="source-category-icon"><RadioTower size={18} aria-hidden="true" /></span><div><h3>Telemetry</h3><p>OTLP and OpenInference traces.</p></div><span className="planned-badge">Planned</span></article>
      </div>

      <div className="source-workspace-grid">
        <form className="source-upload-panel" onSubmit={(event) => { void submit(event) }}>
          <div className="source-panel-heading"><span className="source-category-icon"><FileUp size={18} aria-hidden="true" /></span><div><h2>Add context</h2><p>Upload a UTF-8 text file up to 2 MiB. Files are stored without executing or interpreting them.</p></div></div>
          <fieldset className="source-kind-options">
            <legend>Source type</legend>
            {(Object.keys(sourceKindLabels) as SourceKind[]).map((value) => (
              <label className={kind === value ? 'source-kind-selected' : ''} key={value}>
                <input type="radio" name="sourceKind" value={value} checked={kind === value} onChange={() => setKind(value)} />
                <span>{sourceKindLabels[value]}</span>
              </label>
            ))}
          </fieldset>
          <label className="source-file-field">
            <span>Source file</span>
            <input
              ref={fileInputRef}
              type="file"
              aria-label="Source file"
              accept=".txt,.md,.json,.yaml,.yml,text/plain,text/markdown,application/json,application/yaml"
              disabled={!canManageSources || isUploadPending}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            <small>Accepted: TXT, Markdown, JSON, YAML. Binary and executable files are rejected.</small>
          </label>
          {file && <div className="upload-file-summary"><FileText size={16} aria-hidden="true" /><span><strong>{file.name}</strong><small>{formatBytes(file.size)}</small></span></div>}
          {uploadError && <div className="form-error" role="alert"><AlertCircle size={17} aria-hidden="true" /><span>{uploadError instanceof ApiError ? uploadError.message : 'The source could not be uploaded. Try again.'}</span></div>}
          {!canManageSources && <p className="source-permission-note">You have read-only access to sources.</p>}
          <button className="primary-button source-upload-action" type="submit" disabled={!file || !canManageSources || isUploadPending}>
            {isUploadPending ? 'Uploading…' : 'Upload source'}
          </button>
        </form>

        <section className="source-inventory" aria-labelledby="source-inventory-title">
          <div className="source-inventory-heading"><div><h2 id="source-inventory-title">Connected sources</h2><p>Stored artifacts remain attributable to this system.</p></div><span>{sources.length}</span></div>
          {!canReadSources && <div className="source-empty"><p>Source read access is not assigned.</p></div>}
          {canReadSources && isSourcesPending && <div className="source-empty" role="status"><p>Loading sources…</p></div>}
          {canReadSources && isSourcesError && <div className="source-empty" role="alert"><p>Sources are temporarily unavailable.</p><button className="secondary-button" type="button" onClick={onRetrySources}>Retry</button></div>}
          {canReadSources && !isSourcesPending && !isSourcesError && sources.length === 0 && <div className="source-empty"><Cloud size={22} aria-hidden="true" /><p>No sources connected yet.</p><span>Start with a requirement, policy, or API contract.</span></div>}
          {canReadSources && !isSourcesPending && !isSourcesError && sources.length > 0 && (
            <ul className="source-list">
              {sources.map((source) => (
                <li key={source.id}><span className="source-list-icon"><FileText size={17} aria-hidden="true" /></span><div><strong>{source.originalFilename}</strong><small>{sourceKindLabels[source.kind]} · {formatBytes(source.byteSize)}</small></div><span className="stored-state"><CheckCircle2 size={13} aria-hidden="true" />Stored</span></li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </section>
  )
}
