// Shared badge/formatting helpers, used by more than one view.
import type { AuditFinding, CertSummary, TlsHealth } from './api'
import type { BadgeColor } from './catalyst'

export interface Badge {
  text: string
  color: BadgeColor
  title?: string
}

export function fmtDate(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

export function healthBadge(h: TlsHealth | 'loading' | undefined): Badge {
  if (h === 'loading' || h === undefined) return { text: '…', color: 'zinc' }
  if (!h.reachable)
    return {
      text: 'unreachable',
      color: 'zinc',
      title: h.error || undefined,
    }
  if (h.expired) return { text: 'expired', color: 'red' }
  const days = h.days_remaining ?? 0
  const title = h.tls_version ? `Negotiated ${h.tls_version}` : undefined
  if (days < 14)
    return {
      text: `${days}d left`,
      color: 'amber',
      title,
    }
  return {
    text: `${days}d left`,
    color: 'green',
    title,
  }
}

// Badge for a certificate's stored expiry (as opposed to a live TLS probe).
export function expiryBadge(cert: CertSummary): Badge {
  if (cert.expired) return { text: 'expired', color: 'red' }
  const days = cert.days_until_expiry
  const color = cert.expiring_soon ? 'amber' : 'green'
  return { text: days != null ? `${days}d left` : 'valid', color }
}

const AUDIT_LABELS: Record<string, string> = {
  not_latest_certificate: 'stale cert',
  third_party_issuer: 'foreign cert',
  unknown_certificate: 'unknown cert',
  renewal_overdue: 'renewal overdue',
}

export function auditBadge(findings: AuditFinding[]): Badge | null {
  if (findings.length === 0) return null
  const worst = findings.some((f) => f.severity === 'error') ? 'error' : 'warning'
  return {
    text: findings.map((f) => AUDIT_LABELS[f.code] || f.code).join(' · '),
    color: worst === 'error' ? 'red' : 'amber',
    title: findings.map((f) => f.message).join('\n\n'),
  }
}
