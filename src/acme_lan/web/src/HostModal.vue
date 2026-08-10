<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { api, type Credential, type DeployPluginSpec, type ManagedHost, type PluginField } from './api'
import {
  Button,
  Checkbox,
  CheckboxField,
  Description,
  Dialog,
  DialogActions,
  DialogBody,
  DialogTitle,
  Field,
  FieldGroup,
  Fieldset,
  Input,
  Label,
  Legend,
  Notice,
  Select,
  Text,
  Textarea,
} from './catalyst'

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
// Per-field config values, keyed by the plugin field's key. Booleans are kept as the
// strings 'true' / '' so the save path can treat every value uniformly.
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

</script>

<template>
  <Dialog :open="true" size="2xl" data-testid="host-modal" @close="emit('close')">
    <DialogTitle>{{ isEdit ? 'Edit host' : 'Add host' }}</DialogTitle>
    <DialogBody>
      <div class="space-y-6">
        <div class="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <Field>
            <Label>Name</Label>
            <Input v-model="form.name" placeholder="esxi01" />
          </Field>
          <Field>
            <Label>Address</Label>
            <Input v-model="form.address" placeholder="192.168.3.5" />
          </Field>
          <Field class="sm:col-span-2">
            <Label>Domains (comma-separated)</Label>
            <Input v-model="form.domains" placeholder="esxi01.lan" />
          </Field>
          <Field>
            <Label>Port</Label>
            <Input v-model="form.port" type="number" />
          </Field>
          <Field>
            <Label>Deploy plugin</Label>
            <Select v-model="form.deploy_plugin" data-testid="plugin-select">
              <option v-for="p in plugins" :key="p.name" :value="p.name">{{ p.name }}</option>
            </Select>
          </Field>
          <Field>
            <Label>CSR source</Label>
            <Select v-model="form.csr_source" data-testid="csr-source-select">
              <option value="device" :disabled="!supportsDevice">device (key stays on device)</option>
              <option value="local">local (acme-lan holds key)</option>
            </Select>
          </Field>
          <Field>
            <Label>Credential (optional)</Label>
            <Select v-model="form.credential_id" data-testid="credential-select">
              <option value="">— none —</option>
              <option v-for="c in credentials" :key="c.id" :value="c.id">
                {{ c.name }} ({{ c.username }})
              </option>
            </Select>
          </Field>
        </div>

        <Notice v-if="form.csr_source === 'local'" color="amber">
          ⚠ With <b>local</b> CSR source, acme-lan generates and stores the private key. Prefer
          <b>device</b> so the private key never leaves the device.
        </Notice>

        <!-- Plugin-specific config, rendered as real form fields and updated as the plugin
             type / CSR mode changes. -->
        <Fieldset>
          <Legend>{{ form.deploy_plugin }} configuration</Legend>
          <Text v-if="visibleFields.length === 0">This plugin needs no extra configuration.</Text>
          <FieldGroup class="space-y-6">
            <template v-for="f in visibleFields" :key="f.key">
              <!-- Booleans render as a real checkbox with the label beside it, not above. -->
              <CheckboxField v-if="f.type === 'checkbox'">
                <Checkbox
                  :model-value="config[f.key] === 'true'"
                  :data-testid="`cfg-${f.key}`"
                  @update:model-value="config[f.key] = $event ? 'true' : ''"
                />
                <Label>{{ f.label }}</Label>
                <Description v-if="f.help">{{ f.help }}</Description>
              </CheckboxField>
              <Field v-else>
                <Label>
                  {{ f.label }}<span v-if="f.required" class="text-red-500">&nbsp;*</span>
                </Label>
                <Textarea
                  v-if="f.type === 'textarea'"
                  v-model="config[f.key]"
                  :placeholder="f.placeholder"
                  rows="2"
                />
                <Input
                  v-else
                  v-model="config[f.key]"
                  :type="f.type === 'number' ? 'number' : f.type === 'password' ? 'password' : 'text'"
                  :placeholder="f.placeholder"
                  :data-testid="`cfg-${f.key}`"
                />
                <Description v-if="f.help">{{ f.help }}</Description>
              </Field>
            </template>
          </FieldGroup>
        </Fieldset>

        <Notice v-if="errorMsg" color="red">{{ errorMsg }}</Notice>
      </div>
    </DialogBody>

    <DialogActions>
      <Button plain @click="emit('close')">Cancel</Button>
      <Button :disabled="saving" @click="save">
        {{ isEdit ? 'Save changes' : 'Add host' }}
      </Button>
    </DialogActions>
  </Dialog>
</template>
