<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import {
  api,
  getToken,
  setToken,
  type Certificate,
  type ManagedHost,
  type Stats,
  type TlsHealth,
} from './api'

const stats = ref<Stats | null>(null)
const certificates = ref<Certificate[]>([])
const health = reactive<Record<string, TlsHealth | 'loading' | undefined>>({})
const error = ref<string>('')
const token = ref<string>(getToken())

const hosts = ref<ManagedHost[]>([])
const hostMsg = ref<string>('')
const newHost = reactive({ name: '', domains: '', address: '', port: 443, deploy_plugin: 'local', config: '' })

const probeForm = reactive({ host: '', port: 443, server_name: '' })
const probeResult = ref<TlsHealth | null>(null)
const probeError = ref<string>('')

async function loadAll() {
  error.value = ''
  try {
    stats.value = await api.stats()
    certificates.value = await api.certificates()
    hosts.value = await api.hosts().catch(() => [])
    // Kick off a realtime health probe for every certificate.
    for (const cert of certificates.value) checkHealth(cert.id)
  } catch (e: any) {
    error.value = e.message || String(e)
  }
}

async function addHost() {
  hostMsg.value = ''
  try {
    await api.createHost({
      name: newHost.name,
      domains: newHost.domains.split(',').map((s) => s.trim()).filter(Boolean),
      address: newHost.address,
      port: Number(newHost.port),
      deploy_plugin: newHost.deploy_plugin,
      config: newHost.config ? JSON.parse(newHost.config) : {},
    } as any)
    hosts.value = await api.hosts()
    newHost.name = ''
    newHost.domains = ''
    newHost.address = ''
    newHost.config = ''
  } catch (e: any) {
    hostMsg.value = e.message || String(e)
  }
}

async function renewHost(id: string) {
  hostMsg.value = 'renewing…'
  try {
    const r = await api.renewHost(id)
    hostMsg.value = r.ok ? 'renewed & deployed' : `error: ${r.detail}`
    hosts.value = await api.hosts()
  } catch (e: any) {
    hostMsg.value = e.message || String(e)
  }
}

async function removeHost(id: string) {
  await api.deleteHost(id)
  hosts.value = await api.hosts()
}

async function checkHealth(id: string) {
  health[id] = 'loading'
  try {
    health[id] = await api.certificateHealth(id)
  } catch (e: any) {
    health[id] = { host: '', port: 0, reachable: false, error: e.message }
  }
}

async function runProbe() {
  probeError.value = ''
  probeResult.value = null
  try {
    probeResult.value = await api.probe(
      probeForm.host,
      Number(probeForm.port),
      probeForm.server_name || undefined,
    )
  } catch (e: any) {
    probeError.value = e.message || String(e)
  }
}

function saveToken() {
  setToken(token.value)
  loadAll()
}

function healthBadge(h: TlsHealth | 'loading' | undefined): { text: string; cls: string } {
  if (h === 'loading' || h === undefined) return { text: '…', cls: 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300' }
  if (!h.reachable) return { text: 'unreachable', cls: 'bg-slate-300 text-slate-700 dark:bg-slate-600 dark:text-slate-200' }
  if (h.expired) return { text: 'expired', cls: 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300' }
  const days = h.days_remaining ?? 0
  if (days < 14) return { text: `${days}d left`, cls: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300' }
  return { text: `${days}d left`, cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300' }
}

function fmtDate(s: string | null | undefined): string {
  if (!s) return '—'
  return new Date(s).toLocaleString()
}

onMounted(loadAll)
</script>

<template>
  <div class="min-h-screen bg-slate-50 text-slate-800 dark:bg-slate-900 dark:text-slate-100">
    <header class="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
      <div class="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-4">
        <div class="flex items-center gap-3">
          <div class="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600 font-bold text-white">🔒</div>
          <div>
            <h1 class="text-lg font-semibold">acme-lan</h1>
            <p class="text-xs text-slate-500 dark:text-slate-400">Internal ACME server · certificate dashboard</p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <input
            v-model="token"
            type="password"
            placeholder="admin token (if set)"
            class="w-44 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-800"
          />
          <button
            @click="saveToken"
            class="rounded-md bg-indigo-600 px-3 py-1 text-sm font-medium text-white hover:bg-indigo-500"
          >
            Refresh
          </button>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-6xl space-y-8 px-6 py-8">
      <div v-if="error" class="rounded-md bg-red-100 px-4 py-3 text-sm text-red-700 dark:bg-red-900/40 dark:text-red-300">
        {{ error }}
      </div>

      <!-- Stats -->
      <section class="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <div class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
          <div class="text-2xl font-semibold">{{ stats?.certificates_total ?? '—' }}</div>
          <div class="text-xs text-slate-500 dark:text-slate-400">Certificates issued</div>
        </div>
        <div class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
          <div class="text-2xl font-semibold">{{ stats?.orders_total ?? '—' }}</div>
          <div class="text-xs text-slate-500 dark:text-slate-400">Orders total</div>
        </div>
        <div class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
          <div class="text-2xl font-semibold">{{ stats?.orders_by_status?.valid ?? 0 }}</div>
          <div class="text-xs text-slate-500 dark:text-slate-400">Orders valid</div>
        </div>
      </section>

      <!-- Certificates -->
      <section>
        <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Certificates</h2>
        <div class="overflow-x-auto rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
          <table class="w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase text-slate-500 dark:border-slate-800 dark:text-slate-400">
              <tr>
                <th class="px-4 py-3">Domain(s)</th>
                <th class="px-4 py-3">Live health</th>
                <th class="px-4 py-3">Trusted</th>
                <th class="px-4 py-3">Expires</th>
                <th class="px-4 py-3">Issued</th>
                <th class="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="certificates.length === 0">
                <td colspan="6" class="px-4 py-6 text-center text-slate-400">No certificates issued yet.</td>
              </tr>
              <tr
                v-for="cert in certificates"
                :key="cert.id"
                class="border-b border-slate-100 last:border-0 dark:border-slate-800/60"
              >
                <td class="px-4 py-3 font-medium">
                  {{ cert.primary_domain }}
                  <span v-if="cert.domains.length > 1" class="text-xs text-slate-400">+{{ cert.domains.length - 1 }}</span>
                </td>
                <td class="px-4 py-3">
                  <span class="rounded-full px-2 py-0.5 text-xs font-medium" :class="healthBadge(health[cert.id]).cls">
                    {{ healthBadge(health[cert.id]).text }}
                  </span>
                </td>
                <td class="px-4 py-3">
                  <span v-if="health[cert.id] && health[cert.id] !== 'loading'">
                    {{ (health[cert.id] as TlsHealth).chain_trusted ? '✓' : '✗' }}
                  </span>
                  <span v-else class="text-slate-400">—</span>
                </td>
                <td class="px-4 py-3 text-slate-500 dark:text-slate-400">{{ fmtDate(cert.not_after) }}</td>
                <td class="px-4 py-3 text-slate-500 dark:text-slate-400">{{ fmtDate(cert.issued_at) }}</td>
                <td class="px-4 py-3 text-right">
                  <button @click="checkHealth(cert.id)" class="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                    re-check
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Managed hosts -->
      <section>
        <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Managed hosts</h2>
        <p class="mb-3 text-xs text-slate-400">Devices that can't run ACME (ESXi, printers, switches). acme-lan issues the cert and pushes it via a deploy plugin.</p>
        <div class="overflow-x-auto rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
          <table class="w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase text-slate-500 dark:border-slate-800 dark:text-slate-400">
              <tr>
                <th class="px-4 py-3">Name</th>
                <th class="px-4 py-3">Domain(s)</th>
                <th class="px-4 py-3">Target</th>
                <th class="px-4 py-3">Plugin</th>
                <th class="px-4 py-3">Last status</th>
                <th class="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="hosts.length === 0">
                <td colspan="6" class="px-4 py-6 text-center text-slate-400">No managed hosts yet.</td>
              </tr>
              <tr v-for="host in hosts" :key="host.id" class="border-b border-slate-100 last:border-0 dark:border-slate-800/60">
                <td class="px-4 py-3 font-medium">{{ host.name }}</td>
                <td class="px-4 py-3">{{ host.domains.join(', ') }}</td>
                <td class="px-4 py-3 text-slate-500 dark:text-slate-400">{{ host.address }}:{{ host.port }}</td>
                <td class="px-4 py-3"><code class="text-xs">{{ host.deploy_plugin }}</code></td>
                <td class="px-4 py-3 text-xs text-slate-500 dark:text-slate-400">{{ host.last_status || '—' }}</td>
                <td class="px-4 py-3 text-right whitespace-nowrap">
                  <button @click="renewHost(host.id)" class="mr-3 text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">renew</button>
                  <button @click="removeHost(host.id)" class="text-xs font-medium text-red-600 hover:underline dark:text-red-400">delete</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="mt-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
          <div class="flex flex-wrap items-end gap-3">
            <label class="text-xs"><span class="mb-1 block text-slate-500 dark:text-slate-400">Name</span>
              <input v-model="newHost.name" class="w-32 rounded-md border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800" /></label>
            <label class="text-xs"><span class="mb-1 block text-slate-500 dark:text-slate-400">Domains (comma-sep)</span>
              <input v-model="newHost.domains" placeholder="esxi01.lan" class="w-48 rounded-md border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800" /></label>
            <label class="text-xs"><span class="mb-1 block text-slate-500 dark:text-slate-400">Address</span>
              <input v-model="newHost.address" placeholder="192.168.3.5" class="w-36 rounded-md border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800" /></label>
            <label class="text-xs"><span class="mb-1 block text-slate-500 dark:text-slate-400">Plugin</span>
              <input v-model="newHost.deploy_plugin" class="w-24 rounded-md border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800" /></label>
            <label class="text-xs"><span class="mb-1 block text-slate-500 dark:text-slate-400">Config (JSON)</span>
              <input v-model="newHost.config" placeholder='{"cert_path":"…","key_path":"…"}' class="w-64 rounded-md border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800" /></label>
            <button @click="addHost" class="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500">Add host</button>
          </div>
          <div v-if="hostMsg" class="mt-2 text-xs text-slate-500 dark:text-slate-400">{{ hostMsg }}</div>
        </div>
      </section>

      <!-- Ad-hoc probe -->
      <section>
        <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Probe any TLS endpoint</h2>
        <div class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
          <div class="flex flex-wrap items-end gap-3">
            <label class="text-xs">
              <span class="mb-1 block text-slate-500 dark:text-slate-400">Host</span>
              <input v-model="probeForm.host" placeholder="ldap.lan" class="w-48 rounded-md border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800" />
            </label>
            <label class="text-xs">
              <span class="mb-1 block text-slate-500 dark:text-slate-400">Port</span>
              <input v-model="probeForm.port" type="number" class="w-24 rounded-md border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800" />
            </label>
            <label class="text-xs">
              <span class="mb-1 block text-slate-500 dark:text-slate-400">SNI (optional)</span>
              <input v-model="probeForm.server_name" placeholder="defaults to host" class="w-48 rounded-md border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800" />
            </label>
            <button @click="runProbe" class="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500">Probe</button>
          </div>
          <p class="mt-2 text-xs text-slate-400">Does a raw TLS handshake — works for LDAPS, SMTPS, and any TLS port, not just HTTPS.</p>

          <div v-if="probeError" class="mt-3 rounded-md bg-red-100 px-3 py-2 text-xs text-red-700 dark:bg-red-900/40 dark:text-red-300">{{ probeError }}</div>
          <pre v-if="probeResult" class="mt-3 overflow-x-auto rounded-md bg-slate-100 p-3 text-xs dark:bg-slate-800">{{ JSON.stringify(probeResult, null, 2) }}</pre>
        </div>
      </section>
    </main>
  </div>
</template>
