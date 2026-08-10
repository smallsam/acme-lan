<script setup lang="ts">
// Certificate list: search / sort / paging, live TLS health, deployment audit, and the
// details modal. Superseded certificates (renewed away) are hidden unless asked for.
import { onMounted, reactive, ref, watch } from 'vue'
import {
  api,
  type AuditFinding,
  type Certificate,
  type CertificateDetail,
  type Stats,
  type TlsHealth,
} from './api'
import {
  Badge,
  BadgeButton,
  Button,
  Checkbox,
  CheckboxField,
  DescriptionDetails,
  DescriptionList,
  DescriptionTerm,
  Dialog,
  DialogActions,
  DialogBody,
  DialogTitle,
  Divider,
  Dropdown,
  DropdownButton,
  DropdownItem,
  DropdownLabel,
  DropdownMenu,
  Field,
  Heading,
  Input,
  Label,
  Notice,
  Subheading,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Text,
} from './catalyst'
import { auditBadge, fmtDate, healthBadge } from './format'
import ListControls from './ListControls.vue'
import ListPagination from './ListPagination.vue'

const stats = ref<Stats | null>(null)
const certificates = ref<Certificate[]>([])
const health = reactive<Record<string, TlsHealth | 'loading' | undefined>>({})
const error = ref('')

const query = reactive({
  search: '',
  sort: 'issued_at',
  order: 'desc' as 'asc' | 'desc',
  limit: 25,
  offset: 0,
})
const total = ref(0)
const includeSuperseded = ref(false)

const SORTS = [
  { value: 'issued_at', label: 'Sort: issued' },
  { value: 'not_after', label: 'Sort: expires' },
  { value: 'subject', label: 'Sort: subject' },
]

async function load() {
  error.value = ''
  try {
    const page = await api.certificates({
      ...query,
      include_superseded: includeSuperseded.value,
    })
    certificates.value = page.items
    total.value = page.total
    for (const cert of page.items) checkHealth(cert.id)
  } catch (e: any) {
    error.value = e.message || String(e)
  }
}

async function loadStats() {
  try {
    stats.value = await api.stats()
  } catch {
    stats.value = null
  }
}

watch(
  () => [query.search, query.sort, query.order, query.limit, query.offset, includeSuperseded.value],
  load,
)

async function checkHealth(id: string) {
  health[id] = 'loading'
  try {
    health[id] = await api.certificateHealth(id)
  } catch (e: any) {
    health[id] = { host: '', port: 0, reachable: false, error: e.message }
  }
}

function findings(id: string): AuditFinding[] {
  const h = health[id]
  if (!h || h === 'loading') return []
  return h.deployment?.findings ?? []
}

// --- health-check port, stored per hostname so it survives renewals ---
const editingPort = ref<string | null>(null)
const portDraft = ref<string | number>('')

function openPortEditor(cert: Certificate) {
  editingPort.value = cert.id
  portDraft.value = cert.check_port != null ? String(cert.check_port) : ''
}

async function saveCheckPort(cert: Certificate) {
  const raw = String(portDraft.value).trim()
  const port = raw === '' ? null : Number(raw)
  if (port !== null && (!Number.isInteger(port) || port < 1 || port > 65535)) return
  try {
    const updated = await api.setCheckPort(cert.id, port)
    cert.check_port = updated.check_port
    editingPort.value = null
    checkHealth(cert.id)
  } catch (e: any) {
    error.value = e.message || String(e)
  }
}

function displayPort(cert: Certificate): string {
  if (cert.check_port != null) return String(cert.check_port)
  const h = health[cert.id]
  if (h && h !== 'loading' && h.port) return String(h.port)
  return 'auto'
}

// --- details modal ---
const viewingCert = ref<CertificateDetail | null>(null)
const viewingCertError = ref('')

async function openCertDetails(cert: Certificate) {
  viewingCertError.value = ''
  try {
    viewingCert.value = await api.certificate(cert.id)
  } catch (e: any) {
    error.value = e.message || String(e)
  }
}

async function downloadCert(cert: CertificateDetail, kind: 'leaf' | 'chain') {
  viewingCertError.value = ''
  const base = cert.primary_domain || cert.id
  try {
    await api.downloadCertificate(
      cert.id,
      kind === 'leaf' ? `${base}-cert.pem` : `${base}-chain.pem`,
      kind,
    )
  } catch (e: any) {
    viewingCertError.value = `Download failed: ${e.message || e}`
  }
}

// --- ad-hoc probe ---
const probeForm = reactive({ host: '', port: 443, server_name: '' })
const probeResult = ref<TlsHealth | null>(null)
const probeError = ref('')

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

onMounted(() => {
  loadStats()
  load()
})
defineExpose({ reload: load })
</script>

<template>
  <div class="space-y-10">
    <Notice v-if="error" color="red">{{ error }}</Notice>

    <section>
      <Heading>Overview</Heading>
      <div class="mt-4 grid grid-cols-1 gap-8 sm:grid-cols-3">
        <div>
          <Divider />
          <div class="mt-6 text-lg/6 font-medium sm:text-sm/6">Certificates issued</div>
          <div class="mt-3 text-3xl/8 font-semibold sm:text-2xl/8" data-testid="stat-certificates">
            {{ stats?.certificates_total ?? '—' }}
          </div>
        </div>
        <div>
          <Divider />
          <div class="mt-6 text-lg/6 font-medium sm:text-sm/6">Orders total</div>
          <div class="mt-3 text-3xl/8 font-semibold sm:text-2xl/8">{{ stats?.orders_total ?? '—' }}</div>
        </div>
        <div>
          <Divider />
          <div class="mt-6 text-lg/6 font-medium sm:text-sm/6">Orders valid</div>
          <div class="mt-3 text-3xl/8 font-semibold sm:text-2xl/8">{{ stats?.orders_by_status?.valid ?? 0 }}</div>
        </div>
      </div>
    </section>

    <section class="space-y-6">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <Subheading>Certificates</Subheading>
        <CheckboxField>
          <Checkbox v-model="includeSuperseded" data-testid="show-superseded" />
          <Label>Show superseded (renewed) certificates</Label>
        </CheckboxField>
      </div>

      <ListControls
        v-model:search="query.search"
        v-model:sort="query.sort"
        v-model:order="query.order"
        v-model:limit="query.limit"
        v-model:offset="query.offset"
        :total="total"
        :sorts="SORTS"
        placeholder="Search domain, serial, device…"
      />

      <Table class="[--gutter:--spacing(6)] lg:[--gutter:--spacing(10)]">
        <TableHead>
          <TableRow>
            <TableHeader>Domain(s)</TableHeader>
            <TableHeader>Device</TableHeader>
            <TableHeader>Live health</TableHeader>
            <TableHeader>Deployment</TableHeader>
            <TableHeader>Trusted</TableHeader>
            <TableHeader>Expires</TableHeader>
            <TableHeader>Issued</TableHeader>
            <TableHeader>
              <span class="sr-only">Actions</span>
            </TableHeader>
          </TableRow>
        </TableHead>
        <TableBody>
          <TableRow v-if="certificates.length === 0">
            <TableCell colspan="8" class="text-center text-zinc-500">
              {{ query.search ? 'No certificates match that search.' : 'No certificates issued yet.' }}
            </TableCell>
          </TableRow>
          <TableRow v-for="cert in certificates" :key="cert.id">
            <TableCell class="font-medium">
              <button
                class="hover:underline"
                title="View certificate details"
                @click="openCertDetails(cert)"
              >
                {{ cert.primary_domain }}
              </button>
              <span v-if="cert.domains.length > 1" class="text-zinc-500">+{{ cert.domains.length - 1 }}</span>
              <Badge v-if="cert.retired" color="zinc" class="ml-1">retired</Badge>
            </TableCell>
            <TableCell>
              <Badge v-if="cert.host_name" color="indigo" :title="`Pushed to device ${cert.host_name}`">
                📡 {{ cert.host_name }}
              </Badge>
              <span v-else class="text-zinc-500">— ACME client —</span>
            </TableCell>
            <TableCell>
              <Badge :color="healthBadge(health[cert.id]).color" :title="healthBadge(health[cert.id]).title">
                {{ healthBadge(health[cert.id]).text }}
              </Badge>
              <template v-if="editingPort === cert.id">
                <Input
                  v-model="portDraft"
                  type="number"
                  min="1"
                  max="65535"
                  placeholder="auto"
                  data-testid="check-port-input"
                  class="ml-2 inline-block w-24 align-middle"
                  @keyup.enter="saveCheckPort(cert)"
                  @keyup.escape="editingPort = null"
                />
                <Button plain class="ml-1" @click="saveCheckPort(cert)">Save</Button>
              </template>
              <BadgeButton
                v-else
                color="zinc"
                class="ml-2"
                data-testid="check-port-chip"
                :title="'Health-check port for ' + cert.primary_domain + ' (kept across renewals) — click to edit; empty resets to default'"
                @click="openPortEditor(cert)"
              >
                :{{ displayPort(cert) }}
              </BadgeButton>
            </TableCell>
            <TableCell>
              <Badge
                v-if="auditBadge(findings(cert.id))"
                :color="auditBadge(findings(cert.id))!.color"
                :title="auditBadge(findings(cert.id))!.title"
                data-testid="audit-badge"
              >
                ⚠ {{ auditBadge(findings(cert.id))!.text }}
              </Badge>
              <Badge
                v-else-if="(health[cert.id] as TlsHealth)?.deployment?.serving_this"
                color="green"
                title="This is the certificate the endpoint is serving, and renewal is on schedule."
              >
                live
              </Badge>
              <Badge
                v-else-if="(health[cert.id] as TlsHealth)?.deployment?.status === 'ok'"
                color="zinc"
                title="Superseded: a newer certificate for this name is what the endpoint serves."
              >
                superseded
              </Badge>
              <span v-else class="text-zinc-500">—</span>
            </TableCell>
            <TableCell>
              <span v-if="health[cert.id] && health[cert.id] !== 'loading'">
                {{ (health[cert.id] as TlsHealth).chain_trusted ? '✓' : '✗' }}
              </span>
              <span v-else class="text-zinc-500">—</span>
            </TableCell>
            <TableCell class="text-zinc-500">{{ fmtDate(cert.not_after) }}</TableCell>
            <TableCell class="text-zinc-500">{{ fmtDate(cert.issued_at) }}</TableCell>
            <TableCell>
              <div class="-mx-3 -my-1.5 sm:-mx-2.5">
                <Dropdown>
                  <DropdownButton plain aria-label="More options">
                    <svg data-slot="icon" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                      <path d="M2 8a1.5 1.5 0 1 1 3 0 1.5 1.5 0 0 1-3 0ZM6.5 8a1.5 1.5 0 1 1 3 0 1.5 1.5 0 0 1-3 0ZM11 8a1.5 1.5 0 1 1 3 0 1.5 1.5 0 0 1-3 0Z" />
                    </svg>
                  </DropdownButton>
                  <DropdownMenu anchor="bottom end">
                    <DropdownItem @click="openCertDetails(cert)"><DropdownLabel>View</DropdownLabel></DropdownItem>
                    <DropdownItem @click="checkHealth(cert.id)"><DropdownLabel>Re-check health</DropdownLabel></DropdownItem>
                  </DropdownMenu>
                </Dropdown>
              </div>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>

      <ListPagination v-model:offset="query.offset" :limit="query.limit" :total="total" />
    </section>

    <section class="space-y-4">
      <div>
        <Subheading>Probe any TLS endpoint</Subheading>
        <Text class="mt-1">
          Does a raw TLS handshake — works for LDAPS, SMTPS, and any TLS port, not just HTTPS.
        </Text>
      </div>
      <div class="flex flex-wrap items-end gap-4">
        <Field class="w-48">
          <Label>Host</Label>
          <Input v-model="probeForm.host" placeholder="ldap.lan" />
        </Field>
        <Field class="w-28">
          <Label>Port</Label>
          <Input v-model="probeForm.port" type="number" />
        </Field>
        <Field class="w-48">
          <Label>SNI (optional)</Label>
          <Input v-model="probeForm.server_name" placeholder="defaults to host" />
        </Field>
        <Button @click="runProbe">Probe</Button>
      </div>
      <Notice v-if="probeError" color="red">{{ probeError }}</Notice>
      <pre
        v-if="probeResult"
        class="overflow-x-auto rounded-lg bg-zinc-950/2.5 p-4 font-mono text-xs/5 text-zinc-700 ring-1 ring-zinc-950/5 dark:bg-white/5 dark:text-zinc-300 dark:ring-white/10"
        >{{ JSON.stringify(probeResult, null, 2) }}</pre>
    </section>

    <!-- Certificate details -->
    <Dialog
      :open="viewingCert !== null"
      size="2xl"
      data-testid="cert-modal"
      @close="viewingCert = null"
    >
      <template v-if="viewingCert">
        <DialogTitle>Certificate · {{ viewingCert.primary_domain }}</DialogTitle>
        <DialogBody>
          <DescriptionList v-if="viewingCert.details">
            <template
              v-for="row in [
                ['Common name', viewingCert.details.common_name],
                ['SANs', viewingCert.details.sans.join(', ')],
                ['Organization', viewingCert.details.organization],
                ['Email', viewingCert.details.email],
                ['Issuer', viewingCert.details.issuer],
                ['Serial', viewingCert.details.serial],
                ['Valid from', fmtDate(viewingCert.details.not_before)],
                ['Valid until', fmtDate(viewingCert.details.not_after)],
                ['Subject', viewingCert.details.subject],
              ]"
              :key="row[0] ?? ''"
            >
              <DescriptionTerm>{{ row[0] }}</DescriptionTerm>
              <DescriptionDetails class="break-all whitespace-normal">{{ row[1] || '—' }}</DescriptionDetails>
            </template>
          </DescriptionList>
          <Text v-else>This certificate's PEM could not be parsed.</Text>

          <Notice v-if="viewingCertError" color="red" class="mt-4">{{ viewingCertError }}</Notice>
        </DialogBody>
        <DialogActions>
          <Button plain @click="viewingCert = null">Close</Button>
          <Button
            outline
            data-testid="cert-download-leaf"
            title="Just the end-entity certificate"
            @click="downloadCert(viewingCert, 'leaf')"
          >
            Certificate (.pem)
          </Button>
          <Button
            data-testid="cert-download-chain"
            title="Certificate plus the issuing chain"
            @click="downloadCert(viewingCert, 'chain')"
          >
            Full chain (.pem)
          </Button>
        </DialogActions>
      </template>
    </Dialog>
  </div>
</template>
