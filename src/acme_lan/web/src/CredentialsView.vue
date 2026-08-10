<script setup lang="ts">
// Device credentials used by deploy plugins. Local secrets are stored Fernet-encrypted;
// the remote providers keep the secret in Key Vault / Vault and store only a reference.
import { onMounted, reactive, ref } from 'vue'
import { api, type Credential } from './api'
import {
  Button,
  Code,
  Description,
  Dialog,
  DialogActions,
  DialogBody,
  DialogDescription,
  DialogTitle,
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
  Select,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Text,
  Textarea,
} from './catalyst'

const credentials = ref<Credential[]>([])
const error = ref('')
const notice = ref('')
const adding = ref(false)
const form = reactive({
  name: '',
  kind: 'password',
  username: '',
  provider: 'local',
  secret: '',
  secret_reference: '',
})

async function load() {
  error.value = ''
  try {
    credentials.value = await api.credentials()
  } catch (e: any) {
    error.value = e.message || String(e)
  }
}

async function create() {
  error.value = ''
  notice.value = ''
  try {
    await api.createCredential({ ...form })
    Object.assign(form, {
      name: '', kind: 'password', username: '', provider: 'local',
      secret: '', secret_reference: '',
    })
    adding.value = false
    notice.value = 'Credential saved'
    await load()
  } catch (e: any) {
    error.value = e.message || String(e)
  }
}

async function remove(id: string) {
  error.value = ''
  try {
    await api.deleteCredential(id)
    await load()
  } catch (e: any) {
    error.value = e.message || String(e)
  }
}

onMounted(load)
</script>

<template>
  <section class="space-y-6" data-testid="credentials-view">
    <Notice v-if="error" color="red">{{ error }}</Notice>
    <Notice v-if="notice" color="green">{{ notice }}</Notice>

    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <Heading>Device credentials</Heading>
        <Text class="mt-2">
          Used by deploy plugins to reach a device. Local secrets are encrypted with the
          configured Fernet key; Key Vault and Vault keep the secret themselves and store
          only a reference here.
        </Text>
      </div>
      <Button data-testid="add-credential" @click="adding = true">+ Add credential</Button>
    </div>

    <Table class="[--gutter:--spacing(6)] lg:[--gutter:--spacing(10)]">
      <TableHead>
        <TableRow>
          <TableHeader>Name</TableHeader>
          <TableHeader>Username</TableHeader>
          <TableHeader>Kind</TableHeader>
          <TableHeader>Stored in</TableHeader>
          <TableHeader>
            <span class="sr-only">Actions</span>
          </TableHeader>
        </TableRow>
      </TableHead>
      <TableBody>
        <TableRow v-if="credentials.length === 0">
          <TableCell colspan="5" class="text-center text-zinc-500">No credentials yet.</TableCell>
        </TableRow>
        <TableRow v-for="cred in credentials" :key="cred.id">
          <TableCell class="font-medium">{{ cred.name }}</TableCell>
          <TableCell>{{ cred.username || '—' }}</TableCell>
          <TableCell><Code>{{ cred.kind }}</Code></TableCell>
          <TableCell><Code>{{ cred.provider }}</Code></TableCell>
          <TableCell>
            <div class="-mx-3 -my-1.5 sm:-mx-2.5">
              <Dropdown>
                <DropdownButton plain aria-label="More options">
                  <svg data-slot="icon" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                    <path d="M2 8a1.5 1.5 0 1 1 3 0 1.5 1.5 0 0 1-3 0ZM6.5 8a1.5 1.5 0 1 1 3 0 1.5 1.5 0 0 1-3 0ZM11 8a1.5 1.5 0 1 1 3 0 1.5 1.5 0 0 1-3 0Z" />
                  </svg>
                </DropdownButton>
                <DropdownMenu anchor="bottom end">
                  <DropdownItem @click="remove(cred.id)"><DropdownLabel>Delete</DropdownLabel></DropdownItem>
                </DropdownMenu>
              </Dropdown>
            </div>
          </TableCell>
        </TableRow>
      </TableBody>
    </Table>

    <Dialog :open="adding" size="lg" @close="adding = false">
      <DialogTitle>Add credential</DialogTitle>
      <DialogDescription>
        Deploy plugins use this credential to sign in to the device they push certificates to.
      </DialogDescription>
      <DialogBody>
        <div class="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <Field>
            <Label>Name</Label>
            <Input v-model="form.name" data-testid="cred-name" placeholder="switch-admin" />
          </Field>
          <Field>
            <Label>Username</Label>
            <Input v-model="form.username" data-testid="cred-username" placeholder="admin" />
          </Field>
          <Field>
            <Label>Kind</Label>
            <Select v-model="form.kind" data-testid="cred-kind">
              <option value="password">password</option>
              <option value="ssh_key">ssh_key</option>
            </Select>
          </Field>
          <Field>
            <Label>Stored in</Label>
            <Select v-model="form.provider" data-testid="cred-provider">
              <option value="local">local (encrypted here)</option>
              <option value="azure_keyvault">azure_keyvault</option>
              <option value="vault">vault</option>
            </Select>
          </Field>
          <Field v-if="form.provider === 'local'" class="sm:col-span-2">
            <Label>{{ form.kind === 'ssh_key' ? 'Private key (PEM)' : 'Password' }}</Label>
            <Textarea
              v-if="form.kind === 'ssh_key'"
              v-model="form.secret"
              rows="4"
              data-testid="cred-secret"
              placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
            />
            <Input v-else v-model="form.secret" type="password" data-testid="cred-secret" />
          </Field>
          <Field v-else class="sm:col-span-2">
            <Label>Secret reference</Label>
            <Input
              v-model="form.secret_reference"
              data-testid="cred-reference"
              placeholder="key-vault secret name, or vault path"
            />
            <Description>
              The secret stays in the provider and is fetched at deploy time. Configure the
              provider's URL and token under Settings → Certificate &amp; key storage.
            </Description>
          </Field>
        </div>
      </DialogBody>
      <DialogActions>
        <Button plain @click="adding = false">Cancel</Button>
        <Button data-testid="cred-save" @click="create">Save credential</Button>
      </DialogActions>
    </Dialog>
  </section>
</template>
