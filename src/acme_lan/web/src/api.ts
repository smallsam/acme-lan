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
    throw new Error(`${resp.status} ${resp.statusText} ${text}`)
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
}

export interface Stats {
  orders_total: number
  orders_by_status: Record<string, number>
  certificates_total: number
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
}

export const api = {
  stats: (): Promise<Stats> => fetch('/api/stats', { headers: headers() }).then(handle),
  certificates: (): Promise<Certificate[]> =>
    fetch('/api/certificates', { headers: headers() }).then(handle),
  certificateHealth: (id: string, port?: number): Promise<TlsHealth> => {
    const q = port ? `?port=${port}` : ''
    return fetch(`/api/certificates/${id}/health${q}`, { headers: headers() }).then(handle)
  },
  probe: (host: string, port: number, server_name?: string): Promise<TlsHealth> =>
    fetch('/api/health/probe', {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify({ host, port, server_name }),
    }).then(handle),
  hosts: (): Promise<ManagedHost[]> => fetch('/api/hosts', { headers: headers() }).then(handle),
  createHost: (h: Partial<ManagedHost>): Promise<ManagedHost> =>
    fetch('/api/hosts', { method: 'POST', headers: headers(), body: JSON.stringify(h) }).then(
      handle,
    ),
  deleteHost: (id: string): Promise<void> =>
    fetch(`/api/hosts/${id}`, { method: 'DELETE', headers: headers() }).then((r) => {
      if (!r.ok) throw new Error(`${r.status}`)
    }),
}

export interface ManagedHost {
  id: string
  name: string
  domains: string[]
  address: string
  port: number
  deploy_plugin: string
  enabled: boolean
  last_deployed_at: string | null
  last_status: string | null
}
