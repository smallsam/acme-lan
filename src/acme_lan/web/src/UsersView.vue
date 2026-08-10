<script setup lang="ts">
// Dashboard accounts. Local users sign in with a password; OIDC users are created on
// first successful single sign-on and have no password of their own.
import { onMounted, reactive, ref } from 'vue'
import { api, type AuthStatus, type AuthUser } from './api'
import {
  Badge,
  Button,
  Code,
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
  Strong,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Text,
} from './catalyst'

const props = defineProps<{ status: AuthStatus | null }>()

const users = ref<AuthUser[]>([])
const error = ref('')
const notice = ref('')
const adding = ref(false)
const form = reactive({ username: '', email: '', password: '', confirm: '' })
const resetting = ref<AuthUser | null>(null)
const newPassword = ref('')

async function load() {
  error.value = ''
  try {
    users.value = await api.users()
  } catch (e: any) {
    error.value = e.message || String(e)
  }
}

async function create() {
  error.value = ''
  notice.value = ''
  if (form.password !== form.confirm) {
    error.value = 'The passwords do not match.'
    return
  }
  try {
    await api.createUser({ username: form.username, email: form.email, password: form.password })
    Object.assign(form, { username: '', email: '', password: '', confirm: '' })
    adding.value = false
    notice.value = 'User created'
    await load()
  } catch (e: any) {
    error.value = e.message || String(e)
  }
}

async function toggleDisabled(user: AuthUser) {
  error.value = ''
  try {
    await api.updateUser(user.id, { disabled: !user.disabled })
    await load()
  } catch (e: any) {
    error.value = e.message || String(e)
  }
}

function openReset(user: AuthUser) {
  newPassword.value = ''
  resetting.value = user
}

async function saveNewPassword() {
  const user = resetting.value
  if (!user) return
  error.value = ''
  try {
    await api.updateUser(user.id, { password: newPassword.value })
    resetting.value = null
    newPassword.value = ''
    notice.value = `Password updated for ${user.username}; their sessions were signed out.`
    await load()
  } catch (e: any) {
    error.value = e.message || String(e)
  }
}

async function remove(user: AuthUser) {
  error.value = ''
  try {
    await api.deleteUser(user.id)
    await load()
  } catch (e: any) {
    error.value = e.message || String(e)
  }
}

onMounted(load)
</script>

<template>
  <section class="space-y-6" data-testid="users-view">
    <Notice v-if="error" color="red">{{ error }}</Notice>
    <Notice v-if="notice" color="green">{{ notice }}</Notice>

    <Notice v-if="status && !status.auth_required" color="amber">
      Login is currently optional — anyone who can reach this server can use it. Turn on
      <Strong>Require login</Strong> under Settings → Authentication to enforce it.
    </Notice>

    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <Heading>Users</Heading>
        <Text class="mt-2">
          Local accounts sign in with a password. Single sign-on accounts appear here after
          their first login and are managed in your identity provider.
        </Text>
      </div>
      <Button data-testid="add-user" @click="adding = true">+ Add user</Button>
    </div>

    <Table class="[--gutter:--spacing(6)] lg:[--gutter:--spacing(10)]">
      <TableHead>
        <TableRow>
          <TableHeader>Username</TableHeader>
          <TableHeader>Email</TableHeader>
          <TableHeader>Sign-in</TableHeader>
          <TableHeader>Status</TableHeader>
          <TableHeader>Last login</TableHeader>
          <TableHeader>
            <span class="sr-only">Actions</span>
          </TableHeader>
        </TableRow>
      </TableHead>
      <TableBody>
        <TableRow v-if="users.length === 0">
          <TableCell colspan="6" class="text-center text-zinc-500">No users yet.</TableCell>
        </TableRow>
        <TableRow v-for="user in users" :key="user.id">
          <TableCell class="font-medium">{{ user.username }}</TableCell>
          <TableCell class="text-zinc-500">{{ user.email || '—' }}</TableCell>
          <TableCell><Code>{{ user.provider }}</Code></TableCell>
          <TableCell>
            <Badge :color="user.disabled ? 'red' : 'green'">
              {{ user.disabled ? 'disabled' : 'active' }}
            </Badge>
          </TableCell>
          <TableCell class="text-zinc-500">
            {{ user.last_login_at ? new Date(user.last_login_at).toLocaleString() : 'never' }}
          </TableCell>
          <TableCell>
            <div class="-mx-3 -my-1.5 sm:-mx-2.5">
              <Dropdown>
                <DropdownButton plain aria-label="More options">
                  <svg data-slot="icon" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                    <path d="M2 8a1.5 1.5 0 1 1 3 0 1.5 1.5 0 0 1-3 0ZM6.5 8a1.5 1.5 0 1 1 3 0 1.5 1.5 0 0 1-3 0ZM11 8a1.5 1.5 0 1 1 3 0 1.5 1.5 0 0 1-3 0Z" />
                  </svg>
                </DropdownButton>
                <DropdownMenu anchor="bottom end">
                  <DropdownItem @click="openReset(user)"><DropdownLabel>Set password…</DropdownLabel></DropdownItem>
                  <DropdownItem @click="toggleDisabled(user)">
                    <DropdownLabel>{{ user.disabled ? 'Enable' : 'Disable' }}</DropdownLabel>
                  </DropdownItem>
                  <DropdownItem @click="remove(user)"><DropdownLabel>Delete</DropdownLabel></DropdownItem>
                </DropdownMenu>
              </Dropdown>
            </div>
          </TableCell>
        </TableRow>
      </TableBody>
    </Table>

    <Dialog :open="adding" size="lg" @close="adding = false">
      <DialogTitle>Add user</DialogTitle>
      <DialogDescription>Local accounts sign in with a username and password.</DialogDescription>
      <DialogBody>
        <div class="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <Field>
            <Label>Username</Label>
            <Input v-model="form.username" data-testid="user-name" autocomplete="off" />
          </Field>
          <Field>
            <Label>Email</Label>
            <Input v-model="form.email" type="email" autocomplete="off" />
          </Field>
          <Field>
            <Label>Password (min 8 characters)</Label>
            <Input v-model="form.password" type="password" data-testid="user-password" autocomplete="new-password" />
          </Field>
          <Field>
            <Label>Confirm password</Label>
            <Input v-model="form.confirm" type="password" data-testid="user-confirm" autocomplete="new-password" />
          </Field>
        </div>
      </DialogBody>
      <DialogActions>
        <Button plain @click="adding = false">Cancel</Button>
        <Button data-testid="user-save" @click="create">Create user</Button>
      </DialogActions>
    </Dialog>

    <Dialog :open="resetting !== null" size="sm" @close="resetting = null">
      <DialogTitle>Set password{{ resetting ? ` · ${resetting.username}` : '' }}</DialogTitle>
      <DialogDescription>Saving signs the user out of all of their sessions.</DialogDescription>
      <DialogBody>
        <Field>
          <Label>New password</Label>
          <Input v-model="newPassword" type="password" autocomplete="new-password" @keyup.enter="saveNewPassword" />
        </Field>
      </DialogBody>
      <DialogActions>
        <Button plain @click="resetting = null">Cancel</Button>
        <Button @click="saveNewPassword">Save password</Button>
      </DialogActions>
    </Dialog>
  </section>
</template>
