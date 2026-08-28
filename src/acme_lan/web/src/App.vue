<script setup lang="ts">
// Shell: resolves who's signed in, then shows either the login screen or the dashboard in
// a Catalyst stacked layout — navbar tabs on desktop, slide-in sidebar on mobile, and an
// account dropdown on the right. Each tab is its own view component.
import { computed, onMounted, ref } from 'vue'
import { api, getToken, setToken, type AuthStatus, type ServerInfo } from './api'
import {
  Avatar,
  Button,
  Dialog,
  DialogActions,
  DialogBody,
  DialogDescription,
  DialogTitle,
  Dropdown,
  DropdownButton,
  DropdownDivider,
  DropdownHeader,
  DropdownItem,
  DropdownLabel,
  DropdownMenu,
  Field,
  Input,
  Label,
  Navbar,
  NavbarDivider,
  NavbarItem,
  NavbarLabel,
  NavbarSection,
  NavbarSpacer,
  Notice,
  Sidebar,
  SidebarBody,
  SidebarHeader,
  SidebarItem,
  SidebarLabel,
  SidebarSection,
  StackedLayout,
} from './catalyst'
import CertificatesView from './CertificatesView.vue'
import CredentialsView from './CredentialsView.vue'
import HostsView from './HostsView.vue'
import LoginView from './LoginView.vue'
import SettingsView from './SettingsView.vue'
import UsersView from './UsersView.vue'

type Tab = 'certificates' | 'hosts' | 'credentials' | 'users' | 'settings'

const TABS: { id: Tab; label: string }[] = [
  { id: 'certificates', label: 'Certificates' },
  { id: 'hosts', label: 'Hosts' },
  { id: 'credentials', label: 'Credentials' },
  { id: 'users', label: 'Users' },
  { id: 'settings', label: 'Settings' },
]

const tab = ref<Tab>('certificates')
const authStatus = ref<AuthStatus | null>(null)
const ready = ref(false)
const token = ref(getToken())
const showToken = ref(false)
// An OIDC round trip that failed comes back as ?login_error=…
const loginError = ref(new URLSearchParams(window.location.search).get('login_error') || '')

// When viewed over plain HTTP while a trusted HTTPS listener is up, point at it.
const serverInfo = ref<ServerInfo | null>(null)
const showHttpsBanner = computed(
  () =>
    window.location.protocol === 'http:' &&
    !!serverInfo.value?.tls_active &&
    !!serverInfo.value?.https_url,
)

// Set when the user asks to sign in even though login isn't mandatory.
const forceLogin = ref(false)

// Show the login screen when login is mandatory and nobody is signed in, or on first run
// when there are no accounts at all.
const mustSignIn = computed(() => {
  const status = authStatus.value
  if (!status) return false
  if (status.user) return false
  return status.auth_required || forceLogin.value
})

const userInitials = computed(() => (authStatus.value?.user?.username || '?').slice(0, 2))

async function refreshAuth() {
  try {
    authStatus.value = await api.authStatus()
  } catch {
    // An older server without the auth endpoints: carry on unauthenticated.
    authStatus.value = null
  }
}

async function onSignedIn() {
  loginError.value = ''
  forceLogin.value = false
  // Drop the ?login_error= from the address bar so a refresh doesn't resurrect it.
  window.history.replaceState({}, '', window.location.pathname)
  await refreshAuth()
}

async function signOut() {
  await api.logout().catch(() => {})
  forceLogin.value = false
  await refreshAuth()
  tab.value = 'certificates'
}

function saveToken() {
  setToken(token.value)
  showToken.value = false
  window.location.reload()
}

onMounted(async () => {
  await refreshAuth()
  ready.value = true
  api
    .serverInfo()
    .then((info) => (serverInfo.value = info))
    .catch(() => {})
})
</script>

<template>
  <template v-if="ready">
    <LoginView
      v-if="mustSignIn && authStatus"
      :status="authStatus"
      :initial-error="loginError"
      @signed-in="onSignedIn"
    />

    <StackedLayout v-else>
      <template #navbar>
        <Navbar>
          <NavbarItem @click="tab = 'certificates'">
            <Avatar square initials="al" class="bg-zinc-900 text-white dark:bg-white dark:text-zinc-900" />
            <NavbarLabel>acme-lan</NavbarLabel>
          </NavbarItem>
          <NavbarDivider class="max-lg:hidden" />
          <NavbarSection class="max-lg:hidden">
            <NavbarItem
              v-for="entry in TABS"
              :key="entry.id"
              :current="tab === entry.id"
              :data-testid="`tab-${entry.id}`"
              @click="tab = entry.id"
            >
              {{ entry.label }}
            </NavbarItem>
          </NavbarSection>
          <NavbarSpacer />
          <NavbarSection>
            <NavbarItem
              v-if="authStatus?.token_auth_enabled"
              title="Provide the admin API token for this browser"
              @click="showToken = true"
            >
              <svg data-slot="icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path
                  fill-rule="evenodd"
                  d="M8 7a5 5 0 1 1 3.61 4.804l-1.903 1.903A1 1 0 0 1 9 14H8v1a1 1 0 0 1-1 1H6v1a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-2a1 1 0 0 1 .293-.707L8.196 8.39A5.002 5.002 0 0 1 8 7Zm5-3a.75.75 0 0 0 0 1.5A1.5 1.5 0 0 1 14.5 7 .75.75 0 0 0 16 7a3 3 0 0 0-3-3Z"
                  clip-rule="evenodd"
                />
              </svg>
            </NavbarItem>

            <Dropdown v-if="authStatus?.user">
              <DropdownButton :as="NavbarItem" data-testid="account-menu">
                <Avatar square :initials="userInitials" />
                <svg data-slot="icon" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                  <path
                    fill-rule="evenodd"
                    d="M4.22 6.22a.75.75 0 0 1 1.06 0L8 8.94l2.72-2.72a.75.75 0 1 1 1.06 1.06l-3.25 3.25a.75.75 0 0 1-1.06 0L4.22 7.28a.75.75 0 0 1 0-1.06Z"
                    clip-rule="evenodd"
                  />
                </svg>
              </DropdownButton>
              <DropdownMenu class="min-w-64" anchor="bottom end">
                <DropdownHeader>
                  <div class="pr-6">
                    <div class="text-xs text-zinc-500 dark:text-zinc-400">Signed in as</div>
                    <div class="text-sm/7 font-semibold text-zinc-800 dark:text-white">
                      {{ authStatus.user.username }}
                      <span v-if="authStatus.user.provider === 'oidc'" class="font-normal text-zinc-500">(SSO)</span>
                    </div>
                  </div>
                </DropdownHeader>
                <DropdownDivider />
                <DropdownItem data-testid="sign-out" @click="signOut">
                  <DropdownLabel>Sign out</DropdownLabel>
                </DropdownItem>
              </DropdownMenu>
            </Dropdown>
            <NavbarItem
              v-else-if="authStatus?.oidc_enabled || authStatus?.local_login_enabled"
              data-testid="sign-in"
              @click="forceLogin = true"
            >
              Sign in
            </NavbarItem>
          </NavbarSection>
        </Navbar>
      </template>

      <template #sidebar>
        <Sidebar>
          <SidebarHeader>
            <div class="flex items-center gap-3 px-2 py-1">
              <Avatar square initials="al" class="size-6 bg-zinc-900 text-white dark:bg-white dark:text-zinc-900" />
              <SidebarLabel class="font-semibold">acme-lan</SidebarLabel>
            </div>
          </SidebarHeader>
          <SidebarBody>
            <SidebarSection>
              <SidebarItem
                v-for="entry in TABS"
                :key="entry.id"
                :current="tab === entry.id"
                @click="tab = entry.id"
              >
                <SidebarLabel>{{ entry.label }}</SidebarLabel>
              </SidebarItem>
            </SidebarSection>
          </SidebarBody>
        </Sidebar>
      </template>

      <div class="space-y-6">
        <Notice v-if="showHttpsBanner" color="amber" data-testid="https-banner">
          🔓 You're viewing the dashboard over plain HTTP —
          <a :href="serverInfo!.https_url!" class="font-semibold underline underline-offset-2">
            switch to the trusted HTTPS version
          </a>
        </Notice>
        <Notice v-if="loginError" color="red" data-testid="login-error-banner">
          Sign-in failed: {{ loginError }}
        </Notice>

        <CertificatesView v-if="tab === 'certificates'" />
        <HostsView v-else-if="tab === 'hosts'" />
        <CredentialsView v-else-if="tab === 'credentials'" />
        <UsersView v-else-if="tab === 'users'" :status="authStatus" />
        <SettingsView
          v-else-if="tab === 'settings'"
          :oidc-redirect-uri="authStatus?.oidc_redirect_uri"
        />
      </div>
    </StackedLayout>

    <Dialog :open="showToken" size="sm" @close="showToken = false">
      <DialogTitle>Admin API token</DialogTitle>
      <DialogDescription>
        Stored in this browser and sent with every management request.
      </DialogDescription>
      <DialogBody>
        <Field>
          <Label>Token</Label>
          <Input v-model="token" type="password" placeholder="admin token" />
        </Field>
      </DialogBody>
      <DialogActions>
        <Button plain @click="showToken = false">Cancel</Button>
        <Button @click="saveToken">Use token</Button>
      </DialogActions>
    </Dialog>
  </template>
</template>
