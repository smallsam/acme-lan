<script setup lang="ts">
// Sign-in screen. Doubles as first-run setup when no accounts exist yet.
// Layout follows Catalyst's auth demo: a centred single-column form on the auth layout.
import { ref } from 'vue'
import { api, type AuthStatus } from './api'
import {
  AuthLayout,
  Avatar,
  Button,
  Field,
  Heading,
  Input,
  Label,
  Notice,
  Text,
} from './catalyst'

const props = defineProps<{ status: AuthStatus; initialError?: string }>()
const emit = defineEmits<{ (e: 'signed-in'): void }>()

const username = ref('')
const password = ref('')
const confirm = ref('')
const email = ref('')
const error = ref(props.initialError || '')
const busy = ref(false)

const setup = props.status.needs_setup

async function submit() {
  error.value = ''
  if (setup && password.value !== confirm.value) {
    error.value = 'The passwords do not match.'
    return
  }
  if (setup && password.value.length < 8) {
    error.value = 'Choose a password of at least 8 characters.'
    return
  }
  busy.value = true
  try {
    if (setup) {
      await api.setupFirstUser(username.value, password.value, email.value)
    } else {
      await api.login(username.value, password.value)
    }
    emit('signed-in')
  } catch (e: any) {
    error.value = e.message || String(e)
  } finally {
    busy.value = false
  }
}

</script>

<template>
  <AuthLayout>
    <div class="grid w-full max-w-sm grid-cols-1 gap-8">
      <div class="flex items-center gap-3">
        <Avatar square initials="al" class="size-9 bg-zinc-900 text-white dark:bg-white dark:text-zinc-900" alt="" />
        <div>
          <Heading>acme-lan</Heading>
          <Text>{{ setup ? 'Create the first administrator' : 'Sign in to continue' }}</Text>
        </div>
      </div>

      <Notice v-if="error" color="red" data-testid="login-error">{{ error }}</Notice>

      <form
        v-if="setup || status.local_login_enabled"
        class="grid grid-cols-1 gap-6"
        @submit.prevent="submit"
      >
        <Field>
          <Label>Username</Label>
          <Input v-model="username" data-testid="login-username" autocomplete="username" />
        </Field>
        <Field v-if="setup">
          <Label>Email (optional)</Label>
          <Input v-model="email" type="email" autocomplete="email" />
        </Field>
        <Field>
          <Label>Password</Label>
          <Input v-model="password" data-testid="login-password" type="password" autocomplete="current-password" />
        </Field>
        <Field v-if="setup">
          <Label>Confirm password</Label>
          <Input v-model="confirm" type="password" autocomplete="new-password" />
        </Field>
        <Button type="submit" data-testid="login-submit" :disabled="busy" class="w-full">
          {{ busy ? 'Please wait…' : setup ? 'Create account' : 'Sign in' }}
        </Button>
      </form>

      <Text v-else-if="!status.oidc_enabled">
        No local accounts exist and single sign-on is not configured.
      </Text>

      <div v-if="status.oidc_enabled && !setup">
        <div v-if="status.local_login_enabled" class="mb-6 flex items-center gap-3">
          <span class="h-px flex-1 bg-zinc-950/10 dark:bg-white/10" />
          <Text>or</Text>
          <span class="h-px flex-1 bg-zinc-950/10 dark:bg-white/10" />
        </div>
        <Button outline href="/api/auth/oidc/start" data-testid="oidc-login" class="w-full">
          Sign in with {{ status.oidc_provider === 'entra' ? 'Microsoft Entra ID' : 'single sign-on' }}
        </Button>
      </div>
    </div>
  </AuthLayout>
</template>
