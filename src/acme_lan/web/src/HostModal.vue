<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { api, type Credential, type DeployPluginSpec, type ManagedHost, type PluginField } from './api'

const props = defineProps<{
  // null → add mode; an existing host → edit mode.
  host: ManagedHost | null
  plugins: DeployPluginSpec[]
  credentials: Credential[]
}>()

const emit = defineEmits<{ (e: 'close'): void; (e: 'saved'): void }>()

const isEdit = computed(() => props.host !== null)

const form = reactive({
  name: '',
  domains: '',
  address: '',
  port: 443,
  deploy_plugin: 'local',
  csr_source: 'device',
  credential_id: '' as string,
})
// Per-field config values, keyed by the plugin field's key.
const config = reactive<Record<string, string>>({})
const saving = ref(false)
const errorMsg = ref('')

// Initialise the form from the passed host (edit) or defaults (add).
watch(
  () => props.host,
  (host) => {
    errorMsg.value = ''
    if (host) {
      form.name = host.name
      form.domains = host.domains.join(', ')
      form.address = host.address
      form.port = host.port
      form.deploy_plugin = host.deploy_plugin
      form.csr_source = host.csr_source
      form.credential_id = host.credential_id || ''
      for (const k of Object.keys(config)) delete config[k]
      for (const [k, v] of Object.entries(host.config || {})) config[k] = String(v ?? '')
    } else {
      form.name = ''
      form.domains = ''
      form.address = ''
      form.port = 443
      form.deploy_plugin = 'local'
      form.csr_source = 'device'
      form.credential_id = ''
      for (const k of Object.keys(config)) delete config[k]
    }
  },
  { immediate: true },
)

const selectedPlugin = computed(() =>
  props.plugins.find((p) => p.name === form.deploy_plugin),
)

// The plugin's fields, filtered to the currently-selected CSR mode. This is what makes the
// modal update as you switch plugin type or mode — each plugin declares different config.
const visibleFields = computed<PluginField[]>(() => {
  const p = selectedPlugin.value
  if (!p) return []
  return p.fields.filter((f) => f.modes.includes(form.csr_source))
})

// A device-only plugin can't do local mode, and a plugin that can't fetch a CSR can't do
// device mode. Keep csr_source valid as the plugin changes.
const supportsDevice = computed(() => selectedPlugin.value?.supports_csr_retrieval ?? false)
watch(
  () => form.deploy_plugin,
  () => {
    if (!supportsDevice.value) form.csr_source = 'local'
  },
)

async function save() {
  errorMsg.value = ''
  saving.value = true
  try {
    // Only send config keys relevant to the selected plugin + mode, dropping blanks.
    const cfg: Record<string, string> = {}
    for (const f of visibleFields.value) {
      const v = (config[f.key] ?? '').trim()
      if (v) cfg[f.key] = v
    }
    const payload: Partial<ManagedHost> = {
      name: form.name,
      domains: form.domains.split(',').map((s) => s.trim()).filter(Boolean),
      address: form.address,
      port: Number(form.port),
      deploy_plugin: form.deploy_plugin,
      csr_source: form.csr_source,
      credential_id: form.credential_id || null,
      config: cfg,
    }
    if (isEdit.value && props.host) await api.updateHost(props.host.id, payload)
    else await api.createHost(payload)
    emit('saved')
  } catch (e: any) {
    errorMsg.value = e.message || String(e)
  } finally {
    saving.value = false
  }
}

const inputCls =
  'w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800'
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4 sm:items-center"
    data-testid="host-modal"
    @click.self="emit('close')"
  >
    <div
      class="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-xl dark:border-slate-800 dark:bg-slate-950"
    >
      <div class="mb-4 flex items-center justify-between">
        <h3 class="text-base font-semibold">{{ isEdit ? 'Edit host' : 'Add host' }}</h3>
        <button
          @click="emit('close')"
          class="rounded-md px-2 py-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800"
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      <div class="space-y-4">
        <div class="grid grid-cols-2 gap-3">
          <label class="text-xs">
            <span class="mb-1 block text-slate-500 dark:text-slate-400">Name</span>
            <input v-model="form.name" placeholder="esxi01" :class="inputCls" />
          </label>
          <label class="text-xs">
            <span class="mb-1 block text-slate-500 dark:text-slate-400">Address</span>
            <input v-model="form.address" placeholder="192.168.3.5" :class="inputCls" />
          </label>
          <label class="col-span-2 text-xs">
            <span class="mb-1 block text-slate-500 dark:text-slate-400">Domains (comma-separated)</span>
            <input v-model="form.domains" placeholder="esxi01.lan" :class="inputCls" />
          </label>
          <label class="text-xs">
            <span class="mb-1 block text-slate-500 dark:text-slate-400">Port</span>
            <input v-model="form.port" type="number" :class="inputCls" />
          </label>
          <label class="text-xs">
            <span class="mb-1 block text-slate-500 dark:text-slate-400">Deploy plugin</span>
            <select v-model="form.deploy_plugin" :class="inputCls" data-testid="plugin-select">
              <option v-for="p in plugins" :key="p.name" :value="p.name">{{ p.name }}</option>
            </select>
          </label>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <label class="text-xs">
            <span class="mb-1 block text-slate-500 dark:text-slate-400">CSR source</span>
            <select v-model="form.csr_source" :class="inputCls" data-testid="csr-source-select">
              <option value="device" :disabled="!supportsDevice">device (key stays on device)</option>
              <option value="local">local (acme-lan holds key)</option>
            </select>
          </label>
          <label class="text-xs">
            <span class="mb-1 block text-slate-500 dark:text-slate-400">Credential (optional)</span>
            <select v-model="form.credential_id" :class="inputCls" data-testid="credential-select">
              <option value="">— none —</option>
              <option v-for="c in credentials" :key="c.id" :value="c.id">
                {{ c.name }} ({{ c.username }})
              </option>
            </select>
          </label>
        </div>

        <div
          v-if="form.csr_source === 'local'"
          class="rounded-md bg-amber-100 px-3 py-2 text-xs text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
        >
          ⚠ With <b>local</b> CSR source, acme-lan generates and stores the private key. Prefer
          <b>device</b> so the private key never leaves the device.
        </div>

        <!-- Plugin-specific config, rendered as real form fields and updated as the plugin
             type / CSR mode changes. -->
        <div class="space-y-3 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
          <div class="text-xs font-semibold uppercase tracking-wide text-slate-400">
            {{ form.deploy_plugin }} configuration
          </div>
          <p v-if="visibleFields.length === 0" class="text-xs text-slate-400">
            This plugin needs no extra configuration.
          </p>
          <label v-for="f in visibleFields" :key="f.key" class="block text-xs">
            <span class="mb-1 block text-slate-500 dark:text-slate-400">
              {{ f.label }}<span v-if="f.required" class="text-red-500">&nbsp;*</span>
            </span>
            <textarea
              v-if="f.type === 'textarea'"
              v-model="config[f.key]"
              :placeholder="f.placeholder"
              rows="2"
              :class="inputCls"
            />
            <input
              v-else
              v-model="config[f.key]"
              :type="f.type === 'number' ? 'number' : f.type === 'password' ? 'password' : 'text'"
              :placeholder="f.placeholder"
              :class="inputCls"
            />
            <span v-if="f.help" class="mt-1 block text-[11px] text-slate-400">{{ f.help }}</span>
          </label>
        </div>

        <div
          v-if="errorMsg"
          class="rounded-md bg-red-100 px-3 py-2 text-xs text-red-700 dark:bg-red-900/40 dark:text-red-300"
        >
          {{ errorMsg }}
        </div>
      </div>

      <div class="mt-6 flex justify-end gap-2">
        <button
          @click="emit('close')"
          class="rounded-md border border-slate-300 px-4 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Cancel
        </button>
        <button
          @click="save"
          :disabled="saving"
          class="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {{ isEdit ? 'Save changes' : 'Add host' }}
        </button>
      </div>
    </div>
  </div>
</template>
