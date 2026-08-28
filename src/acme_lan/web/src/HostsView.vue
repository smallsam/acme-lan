<script setup lang="ts">
// Managed hosts (device push): search / sort / paging plus the add-host modal.
import { onMounted, reactive, ref, watch } from 'vue'
import { api, type Credential, type DeployPluginSpec, type ManagedHost } from './api'
import {
  Badge,
  Button,
  Code,
  Dropdown,
  DropdownButton,
  DropdownItem,
  DropdownLabel,
  DropdownMenu,
  Heading,
  Notice,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Text,
} from './catalyst'
import { expiryBadge } from './format'
import HostModal from './HostModal.vue'
import ListControls from './ListControls.vue'
import ListPagination from './ListPagination.vue'

const hosts = ref<ManagedHost[]>([])
const deployPlugins = ref<DeployPluginSpec[]>([])
const credentials = ref<Credential[]>([])
const hostMsg = ref('')
const error = ref('')

const modalOpen = ref(false)
const editingHost = ref<ManagedHost | null>(null)

const query = reactive({
  search: '',
  sort: 'name',
  order: 'asc' as 'asc' | 'desc',
  limit: 25,
  offset: 0,
})
const total = ref(0)

const SORTS = [
  { value: 'name', label: 'Sort: name' },
  { value: 'address', label: 'Sort: address' },
  { value: 'deploy_plugin', label: 'Sort: plugin' },
  { value: 'expires', label: 'Sort: cert expiry' },
  { value: 'last_deployed_at', label: 'Sort: last deployed' },
]

async function load() {
  error.value = ''
  try {
    const page = await api.hosts(query)
    hosts.value = page.items
    total.value = page.total
  } catch (e: any) {
    error.value = e.message || String(e)
  }
}

watch(() => [query.search, query.sort, query.order, query.limit, query.offset], load)

async function loadFormData() {
  deployPlugins.value = await api.deployPlugins().catch(() => [])
  credentials.value = await api.credentials().catch(() => [])
}

function openAddHost() {
  editingHost.value = null
  modalOpen.value = true
}

function openEditHost(host: ManagedHost) {
  editingHost.value = host
  modalOpen.value = true
}

async function onHostSaved() {
  modalOpen.value = false
  hostMsg.value = ''
  await load()
}

async function renewHost(id: string) {
  hostMsg.value = 'renewing…'
  try {
    const result = await api.renewHost(id)
    hostMsg.value = result.ok ? 'renewed & deployed' : `error: ${result.detail}`
    await load()
  } catch (e: any) {
    hostMsg.value = e.message || String(e)
  }
}

async function removeHost(id: string) {
  await api.deleteHost(id)
  await load()
}

onMounted(() => {
  loadFormData()
  load()
})
</script>

<template>
  <section class="space-y-6">
    <Notice v-if="error" color="red">{{ error }}</Notice>

    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <Heading>Managed hosts</Heading>
        <Text class="mt-2">
          Devices that can't run ACME (ESXi, printers, switches). acme-lan issues the cert and
          pushes it via a deploy plugin.
        </Text>
      </div>
      <Button @click="openAddHost">+ Add host</Button>
    </div>

    <ListControls
      v-model:search="query.search"
      v-model:sort="query.sort"
      v-model:order="query.order"
      v-model:limit="query.limit"
      v-model:offset="query.offset"
      :total="total"
      :sorts="SORTS"
      placeholder="Search name, address, plugin…"
    />

    <Table class="[--gutter:--spacing(6)] lg:[--gutter:--spacing(10)]">
      <TableHead>
        <TableRow>
          <TableHeader>Name</TableHeader>
          <TableHeader>Domain(s)</TableHeader>
          <TableHeader>Target</TableHeader>
          <TableHeader>Plugin</TableHeader>
          <TableHeader>Latest cert</TableHeader>
          <TableHeader>Last status</TableHeader>
          <TableHeader>
            <span class="sr-only">Actions</span>
          </TableHeader>
        </TableRow>
      </TableHead>
      <TableBody>
        <TableRow v-if="hosts.length === 0">
          <TableCell colspan="7" class="text-center text-zinc-500">
            {{ query.search ? 'No hosts match that search.' : 'No managed hosts yet.' }}
          </TableCell>
        </TableRow>
        <TableRow v-for="host in hosts" :key="host.id">
          <TableCell class="font-medium">{{ host.name }}</TableCell>
          <TableCell>{{ host.domains.join(', ') }}</TableCell>
          <TableCell class="text-zinc-500">{{ host.address }}:{{ host.port }}</TableCell>
          <TableCell><Code>{{ host.deploy_plugin }}</Code></TableCell>
          <TableCell>
            <Badge
              v-if="host.latest_certificate"
              :color="expiryBadge(host.latest_certificate).color"
              :title="`${host.certificate_count} certificate(s) issued for this device`"
            >
              {{ expiryBadge(host.latest_certificate).text }}
              <span v-if="host.certificate_count > 1" class="opacity-70">· {{ host.certificate_count }}</span>
            </Badge>
            <span v-else class="text-zinc-500">none yet</span>
          </TableCell>
          <TableCell class="text-zinc-500">{{ host.last_status || '—' }}</TableCell>
          <TableCell>
            <div class="-mx-3 -my-1.5 sm:-mx-2.5">
              <Dropdown>
                <DropdownButton plain aria-label="More options">
                  <svg data-slot="icon" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                    <path d="M2 8a1.5 1.5 0 1 1 3 0 1.5 1.5 0 0 1-3 0ZM6.5 8a1.5 1.5 0 1 1 3 0 1.5 1.5 0 0 1-3 0ZM11 8a1.5 1.5 0 1 1 3 0 1.5 1.5 0 0 1-3 0Z" />
                  </svg>
                </DropdownButton>
                <DropdownMenu anchor="bottom end">
                  <DropdownItem @click="openEditHost(host)"><DropdownLabel>Edit</DropdownLabel></DropdownItem>
                  <DropdownItem @click="renewHost(host.id)"><DropdownLabel>Renew now</DropdownLabel></DropdownItem>
                  <DropdownItem @click="removeHost(host.id)"><DropdownLabel>Delete</DropdownLabel></DropdownItem>
                </DropdownMenu>
              </Dropdown>
            </div>
          </TableCell>
        </TableRow>
      </TableBody>
    </Table>

    <ListPagination v-model:offset="query.offset" :limit="query.limit" :total="total" />

    <Text v-if="hostMsg">{{ hostMsg }}</Text>

    <HostModal
      v-if="modalOpen"
      :host="editingHost"
      :plugins="deployPlugins"
      :credentials="credentials"
      @close="modalOpen = false"
      @saved="onHostSaved"
    />
  </section>
</template>
