// Thin fetch wrapper for the acme-lan management API. Sends the admin bearer token
// (stored in localStorage) when one has been entered.

const TOKEN_KEY = 'acme-lan-admin-token'

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token: string): void {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

function headers(): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) h['Authorization'] = `Bearer ${token}`
  return h
}

async function handle(resp: Response) {
  if (!resp.ok) {
    const text = await resp.text().catch(() => '')
    // FastAPI puts the useful message in `detail`; show that rather than raw HTTP noise.
    let message = `${resp.status} ${resp.statusText}`
    try {
      const detail = JSON.parse(text)?.detail
      if (typeof detail === 'string' && detail) message = detail
      else if (Array.isArray(detail) && detail[0]?.msg) message = detail[0].msg
      else if (text) message = `${message}: ${text}`
    } catch {
      if (text) message = `${message}: ${text}`
    }
    throw new Error(message)
  }
  return resp.json()
}

export interface Certificate {
  id: string
  domains: string[]
  primary_domain: string | null
  serial: string | null
  subject: string | null
  not_after: string | null
  issued_at: string | null
  order_status: string | null
  host_id: string | null
  host_name: string | null
  check_port: number | null
  retired?: boolean
  // True when a newer, non-retired certificate exists for the same name.
  superseded?: boolean
  expired?: boolean | null
  expiring_soon?: boolean | null
  days_until_expiry?: number | null
}

export interface Stats {
  orders_total: number
  orders_by_status: Record<string, number>
  certificates_total: number
}

export interface CertificateDetails {
  subject: string
  issuer: string
  common_name: string | null
  organization: string | null
  email: string | null
  serial: string
  not_before: string
  not_after: string
  sans: string[]
}

export interface CertificateDetail extends Certificate {
  pem_chain: string
  details: CertificateDetails | null
}

export interface AuditFinding {
  code: string
  severity: 'info' | 'warning' | 'error'
  message: string
}

// Whether the endpoint is serving the certificate we issued, and whether renewal is
// keeping up — reported independently of trust/expiry.
export interface DeploymentAudit {
  status: 'ok' | 'stale' | 'foreign' | 'unknown' | 'unknown_records'
  matches_issued: boolean | null
  matches_latest: boolean | null
  serving_this: boolean | null
  latest_issued_serial: string | null
  latest_issued_at: string | null
  latest_issued_not_after: string | null
  renewal_overdue: boolean | null
  renewal_due_at: string | null
  findings: AuditFinding[]
}

export interface TlsHealth {
  host: string
  port: number
  reachable: boolean
  error?: string | null
  not_after?: string | null
  days_remaining?: number | null
  expired?: boolean | null
  self_signed?: boolean | null
  chain_trusted?: boolean | null
  san?: string[] | null
  name_matches?: boolean | null
  issuer?: string | null
  serial?: string | null
  deployment?: DeploymentAudit | null
}

export interface ServerInfo {
  tls_active: boolean
  https_url: string | null
}

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface ListQuery {
  search?: string
  sort?: string
  order?: 'asc' | 'desc'
  limit?: number
  offset?: number
  include_superseded?: boolean
}

function qs(query: Record<string, unknown>): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
  }
  const text = params.toString()
  return text ? `?${text}` : ''
}

export interface AuthUser {
  id: string
  username: string
  email: string
  provider: string
  is_admin: boolean
  disabled: boolean
  has_password: boolean
  last_login_at: string | null
}

export interface AuthStatus {
  auth_required: boolean
  local_login_enabled: boolean
  oidc_enabled: boolean
  oidc_provider: string
  token_auth_enabled: boolean
  needs_setup: boolean
  oidc_redirect_uri: string
  user: AuthUser | null
}

// Set when a field only applies given some other choice (e.g. the Cloudflare token is
// only used when the DNS provider is cloudflare).
export interface SettingDependency {
  key: string
  values: string[]
  label: string
  satisfied: boolean
}

export interface SettingField {
  key: string
  env_var: string
  label: string
  subgroup: string
  help: string
  type: 'text' | 'password' | 'boolean' | 'integer' | 'number' | 'json' | 'select'
  choices: string[] | null
  depends_on: SettingDependency | null
  source: 'env' | 'dotenv' | 'file' | 'default'
  editable: boolean
  secret: boolean
  is_set: boolean | null
  value: unknown
  default: unknown
}

export interface SettingsSubgroup {
  title: string
  fields: SettingField[]
}

export interface SettingsGroup {
  id: string
  title: string
  description: string
  fields: SettingField[]
  subgroups: SettingsSubgroup[]
}

export interface SettingsPayload {
  config_file: string
  config_file_exists: boolean
  enforced_count: number
  groups: SettingsGroup[]
}

export interface OidcPreview {
  ok?: boolean
  detail?: string
  provider: string
  discovery_url: string
  redirect_uri: string
  client_id_set: boolean
  client_secret_set: boolean
  issuer?: string
  authorization_endpoint?: string
}

export const api = {
  serverInfo: (): Promise<ServerInfo> => fetch('/api/server-info').then(handle),
  stats: (): Promise<Stats> => fetch('/api/stats', { headers: headers() }).then(handle),
  certificates: (query: ListQuery = {}): Promise<Page<Certificate>> =>
    fetch(`/api/certificates${qs(query)}`, { headers: headers() }).then(handle),

  // --- auth ---
  authStatus: (): Promise<AuthStatus> => fetch('/api/auth/status').then(handle),
  login: (username: string, password: string): Promise<{ user: AuthUser }> =>
    fetch('/api/auth/login', {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify({ username, password }),
    }).then(handle),
  setupFirstUser: (username: string, password: string, email: string): Promise<{ user: AuthUser }> =>
    fetch('/api/auth/setup', {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify({ username, password, email }),
    }).then(handle),
  logout: (): Promise<unknown> =>
    fetch('/api/auth/logout', { method: 'POST', headers: headers() }).then(handle),
  users: (): Promise<AuthUser[]> => fetch('/api/users', { headers: headers() }).then(handle),
  createUser: (body: {
    username: string
    password: string
    email?: string
  }): Promise<AuthUser> =>
    fetch('/api/users', { method: 'POST', headers: headers(), body: JSON.stringify(body) }).then(
      handle,
    ),
  updateUser: (id: string, body: Record<string, unknown>): Promise<AuthUser> =>
    fetch(`/api/users/${id}`, {
      method: 'PATCH',
      headers: headers(),
      body: JSON.stringify(body),
    }).then(handle),
  deleteUser: (id: string): Promise<void> =>
    fetch(`/api/users/${id}`, { method: 'DELETE', headers: headers() }).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
    }),
  oidcPreview: (): Promise<OidcPreview> =>
    fetch('/api/auth/oidc/preview', { headers: headers() }).then(handle),

  // --- settings ---
  settings: (): Promise<SettingsPayload> => fetch('/api/settings', { headers: headers() }).then(handle),
  saveSettings: (values: Record<string, unknown>, unset: string[] = []): Promise<SettingsPayload> =>
    fetch('/api/settings', {
      method: 'PUT',
      headers: headers(),
      body: JSON.stringify({ values, unset }),
    }).then(handle),
  createCredential: (body: Record<string, unknown>): Promise<Credential> =>
    fetch('/api/credentials', {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify(body),
    }).then(handle),
  deleteCredential: (id: string): Promise<void> =>
    fetch(`/api/credentials/${id}`, { method: 'DELETE', headers: headers() }).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
    }),
  certificate: (id: string): Promise<CertificateDetail> =>
    fetch(`/api/certificates/${id}`, { headers: headers() }).then(handle),
  // Download via fetch (not a plain link) so the admin bearer token is sent.
  downloadCertificate: async (
    id: string,
    filename: string,
    kind: 'leaf' | 'chain' = 'chain',
  ): Promise<void> => {
    const resp = await fetch(`/api/certificates/${id}/download?kind=${kind}`, {
      headers: headers(),
    })
    if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`)
    const url = URL.createObjectURL(await resp.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  },
  certificateHealth: (id: string, port?: number): Promise<TlsHealth> => {
    const q = port ? `?port=${port}` : ''
    return fetch(`/api/certificates/${id}/health${q}`, { headers: headers() }).then(handle)
  },
  setCheckPort: (id: string, port: number | null): Promise<Certificate> =>
    fetch(`/api/certificates/${id}/check-port`, {
      method: 'PUT',
      headers: headers(),
      body: JSON.stringify({ port }),
    }).then(handle),
  probe: (host: string, port: number, server_name?: string): Promise<TlsHealth> =>
    fetch('/api/health/probe', {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify({ host, port, server_name }),
    }).then(handle),
  hosts: (query: ListQuery = {}): Promise<Page<ManagedHost>> =>
    fetch(`/api/hosts${qs(query)}`, { headers: headers() }).then(handle),
  createHost: (h: Partial<ManagedHost>): Promise<ManagedHost> =>
    fetch('/api/hosts', { method: 'POST', headers: headers(), body: JSON.stringify(h) }).then(
      handle,
    ),
  updateHost: (id: string, h: Partial<ManagedHost>): Promise<ManagedHost> =>
    fetch(`/api/hosts/${id}`, {
      method: 'PATCH',
      headers: headers(),
      body: JSON.stringify(h),
    }).then(handle),
  deleteHost: (id: string): Promise<void> =>
    fetch(`/api/hosts/${id}`, { method: 'DELETE', headers: headers() }).then((r) => {
      if (!r.ok) throw new Error(`${r.status}`)
    }),
  renewHost: (id: string): Promise<{ ok: boolean; detail: string; certificate_id: string }> =>
    fetch(`/api/hosts/${id}/renew`, { method: 'POST', headers: headers() }).then(handle),
  hostCertificates: (id: string): Promise<CertSummary[]> =>
    fetch(`/api/hosts/${id}/certificates`, { headers: headers() }).then(handle),
  deployPlugins: (): Promise<DeployPluginSpec[]> =>
    fetch('/api/deploy-plugins', { headers: headers() }).then(handle),
  credentials: (): Promise<Credential[]> =>
    fetch('/api/credentials', { headers: headers() }).then(handle),
}

export interface PluginField {
  key: string
  label: string
  type: string
  required: boolean
  modes: string[]
  placeholder: string
  help: string
}

export interface DeployPluginSpec {
  name: string
  supports_csr_retrieval: boolean
  fields: PluginField[]
}

export interface Credential {
  id: string
  name: string
  kind: string
  username: string
  provider: string
}

export interface CertSummary {
  id: string
  primary_domain: string | null
  domains: string[]
  not_after: string | null
  issued_at: string | null
  retired: boolean
  expired?: boolean | null
  expiring_soon?: boolean | null
  days_until_expiry?: number | null
}

export interface ManagedHost {
  id: string
  name: string
  domains: string[]
  address: string
  port: number
  deploy_plugin: string
  csr_source: string
  credential_id: string | null
  config: Record<string, unknown>
  enabled: boolean
  last_deployed_at: string | null
  last_status: string | null
  certificate_count: number
  latest_certificate: CertSummary | null
  warning?: string
}
