<script setup lang="ts">
// Every configuration option, grouped. Two things this screen must be honest about:
//  * Options supplied by the environment are read-only — the dashboard writes a YAML file,
//    and a file cannot override a process's environment.
//  * Options that don't apply to the current choice (the acme-dns fields while Cloudflare
//    is selected, say) are shown greyed out and labelled, rather than hidden — hiding them
//    makes settings appear to vanish.
import { computed, onMounted, ref } from 'vue'
import {
  api,
  type OidcPreview,
  type SettingField,
  type SettingsPayload,
} from './api'
import {
  Badge,
  Button,
  Checkbox,
  Code,
  Divider,
  Input,
  Listbox,
  ListboxLabel,
  ListboxOption,
  Navbar,
  NavbarItem,
  NavbarSection,
  Notice,
  Select,
  Strong,
  Subheading,
  Text,
  type BadgeColor,
} from './catalyst'

// The callback URL comes from auth status so it can be shown before any Test run.
const props = defineProps<{ oidcRedirectUri?: string }>()

const payload = ref<SettingsPayload | null>(null)
const error = ref('')
const notice = ref('')
const busy = ref(false)
const activeGroup = ref('server')
// Only fields the operator actually touched are sent, so untouched secrets keep their value.
const edits = ref<Record<string, unknown>>({})
const oidc = ref<OidcPreview | null>(null)

const groups = computed(() => payload.value?.groups ?? [])
const current = computed(() => groups.value.find((g) => g.id === activeGroup.value) ?? null)
// Fall back to one unnamed section if the server predates sub-sections, so the screen
// still renders every option rather than coming up empty.
const sections = computed(() => {
  const group = current.value
  if (!group) return []
  if (group.subgroups?.length) return group.subgroups
  return [{ title: '', fields: group.fields ?? [] }]
})
const dirty = computed(() => Object.keys(edits.value).length > 0)

async function load() {
  error.value = ''
  try {
    payload.value = await api.settings()
    edits.value = {}
  } catch (e: any) {
    error.value = e.message || String(e)
  }
}

function displayValue(field: SettingField): unknown {
  if (field.key in edits.value) return edits.value[field.key]
  if (field.type === 'json') return JSON.stringify(field.value ?? {})
  if (field.secret) return ''
  return field.value
}

// Relevance is recomputed from unsaved edits too, so switching the provider updates the
// greying immediately rather than after a save.
function applies(field: SettingField): boolean {
  const dependency = field.depends_on
  if (!dependency) return true
  const pending = edits.value[dependency.key]
  if (pending !== undefined) return dependency.values.includes(String(pending))
  return dependency.satisfied
}

function onInput(field: SettingField, raw: unknown) {
  let value: unknown = raw
  if (field.type === 'integer') value = raw === '' ? null : parseInt(String(raw), 10)
  else if (field.type === 'number') value = raw === '' ? null : Number(raw)
  else if (field.type === 'json') {
    try {
      value = JSON.parse(String(raw || '{}'))
    } catch {
      // Keep the raw text so the user can finish typing; save will surface the error.
      value = raw
    }
  }
  edits.value = { ...edits.value, [field.key]: value }
}

async function save() {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    payload.value = await api.saveSettings(edits.value)
    edits.value = {}
    notice.value = `Saved to ${payload.value.config_file}`
  } catch (e: any) {
    error.value = e.message || String(e)
  } finally {
    busy.value = false
  }
}

async function resetToDefault(field: SettingField) {
  busy.value = true
  error.value = ''
  try {
    payload.value = await api.saveSettings({}, [field.key])
    delete edits.value[field.key]
    notice.value = `${field.label} reset to its default`
  } catch (e: any) {
    error.value = e.message || String(e)
  } finally {
    busy.value = false
  }
}

async function testOidc() {
  oidc.value = null
  try {
    oidc.value = await api.oidcPreview()
  } catch (e: any) {
    error.value = e.message || String(e)
  }
}

const sourceBadge: Record<string, { text: string; color: BadgeColor; title: string }> = {
  env: {
    text: 'set by environment',
    color: 'amber',
    title: 'An environment variable defines this value, so it cannot be changed here.',
  },
  dotenv: {
    text: 'set by .env file',
    color: 'amber',
    title: 'A .env file defines this value, so it cannot be changed here.',
  },
  file: {
    text: 'saved',
    color: 'indigo',
    title: 'Stored in the configuration file managed from this screen.',
  },
  default: {
    text: 'default',
    color: 'zinc',
    title: 'Using the built-in default.',
  },
}

onMounted(load)
</script>

<template>
  <section class="space-y-6" data-testid="settings-view">
    <Notice v-if="error" color="red">{{ error }}</Notice>
    <Notice v-if="notice" color="green">{{ notice }}</Notice>

    <div v-if="payload" class="flex flex-wrap items-center justify-between gap-4">
      <Text>
        Saved to <Code data-testid="config-file-path">{{ payload.config_file }}</Code>
        <span v-if="payload.enforced_count">
          · <Strong>{{ payload.enforced_count }}</Strong> option(s) enforced by the environment
        </span>
      </Text>
      <div class="flex items-center gap-3">
        <Button v-if="dirty" plain @click="load">Discard</Button>
        <Button data-testid="settings-save" :disabled="!dirty || busy" @click="save">
          {{ busy ? 'Saving…' : dirty ? `Save ${Object.keys(edits).length} change(s)` : 'Saved' }}
        </Button>
      </div>
    </div>

    <Navbar class="border-b border-zinc-950/5 dark:border-white/5">
      <NavbarSection class="max-w-full flex-wrap">
        <NavbarItem
          v-for="group in groups"
          :key="group.id"
          :current="activeGroup === group.id"
          :data-testid="`settings-tab-${group.id}`"
          @click="activeGroup = group.id"
        >
          {{ group.title }}
        </NavbarItem>
      </NavbarSection>
    </Navbar>

    <div v-if="current" class="space-y-8">
      <Text>{{ current.description }}</Text>

      <!-- Entra ID helper: the redirect URI to paste into the app registration. -->
      <Notice v-if="current.id === 'auth'" color="blue">
        <div class="mb-2 font-semibold">Microsoft Entra ID in three steps</div>
        <ol class="list-decimal space-y-1 pl-4 text-xs/5">
          <li>
            Register an app in Entra and add this <strong>Web</strong> redirect URI:
            <Code data-testid="oidc-redirect-uri">{{ oidc?.redirect_uri || props.oidcRedirectUri || '(set the external URL first)' }}</Code>
          </li>
          <li>Set <em>OIDC provider</em> to <Code>entra</Code> and paste the directory (tenant) ID, client ID and a client secret below.</li>
          <li>Enable OIDC login, save, then use Test to confirm discovery resolves.</li>
        </ol>
        <div class="mt-3 flex flex-wrap items-center gap-2">
          <Button data-testid="oidc-test" @click="testOidc">Test connection</Button>
          <Badge v-if="oidc?.ok === true" color="green">✓ {{ oidc.issuer }}</Badge>
          <Badge v-else-if="oidc?.ok === false" color="red">✗ {{ oidc.detail }}</Badge>
        </div>
      </Notice>

      <div v-for="section in sections" :key="section.title || 'main'" class="space-y-6">
        <template v-if="section.title">
          <Subheading>{{ section.title }}</Subheading>
          <Divider />
        </template>

        <template v-for="field in section.fields" :key="field.key">
          <section
            class="grid gap-x-8 gap-y-4 sm:grid-cols-2"
            :class="applies(field) ? '' : 'opacity-55'"
            :data-testid="`row-${field.key}`"
          >
            <div class="space-y-1">
              <div class="flex flex-wrap items-center gap-2">
                <Subheading :level="3">{{ field.label }}</Subheading>
                <Badge
                  :color="sourceBadge[field.source].color"
                  :title="sourceBadge[field.source].title"
                  :data-testid="`source-${field.key}`"
                >
                  {{ sourceBadge[field.source].text }}
                </Badge>
              </div>
              <div><Code class="text-[10px]">{{ field.env_var }}</Code></div>
              <Text v-if="field.help">{{ field.help }}</Text>
            </div>

            <div class="space-y-2">
              <div class="flex items-center gap-3">
                <Listbox
                  v-if="field.type === 'select'"
                  :model-value="String(displayValue(field) ?? '')"
                  :disabled="!field.editable"
                  :data-testid="`field-${field.key}`"
                  @update:model-value="onInput(field, $event)"
                >
                  <ListboxOption v-for="choice in field.choices || []" :key="choice" :value="choice">
                    <ListboxLabel>{{ choice }}</ListboxLabel>
                  </ListboxOption>
                </Listbox>
                <!-- Booleans: the label already says what the switch does, so no
                     redundant Enabled/Disabled text beside it. -->
                <Checkbox
                  v-else-if="field.type === 'boolean'"
                  :model-value="Boolean(displayValue(field))"
                  :disabled="!field.editable"
                  :data-testid="`field-${field.key}`"
                  @update:model-value="onInput(field, $event)"
                />
                <Input
                  v-else
                  :model-value="(displayValue(field) as string | number | null) ?? ''"
                  :type="field.type === 'password' ? 'password' : field.type === 'integer' || field.type === 'number' ? 'number' : 'text'"
                  :placeholder="field.secret && field.is_set ? '•••••••• (set — type to replace)' : String(field.default ?? '')"
                  :disabled="!field.editable"
                  :data-testid="`field-${field.key}`"
                  @update:model-value="onInput(field, $event)"
                />
                <Button
                  v-if="field.editable && field.source === 'file'"
                  plain
                  title="Remove from the config file and use the built-in default"
                  @click="resetToDefault(field)"
                >
                  Reset
                </Button>
              </div>

              <Text
                v-if="!applies(field) && field.depends_on"
                :data-testid="`inactive-${field.key}`"
              >
                Not in use — applies when {{ field.depends_on.label }} is
                <Code>{{ field.depends_on.values.join(' or ') }}</Code>.
              </Text>
              <Text v-if="!field.editable" class="!text-amber-700 dark:!text-amber-400">
                Enforced by <Code>{{ field.env_var }}</Code> in the environment —
                change it where the container's environment is defined, not here.
              </Text>
            </div>
          </section>
          <Divider soft />
        </template>
      </div>
    </div>
  </section>
</template>
