// Vue port of Catalyst's stacked-layout.tsx: navbar on top, content in the framed white
// panel, and a slide-in drawer for the sidebar slot on mobile.
import { defineComponent, h, provide, ref, type InjectionKey } from 'vue'
import { Dialog as HDialog, DialogPanel, TransitionChild, TransitionRoot } from '@headlessui/vue'
import { NavbarItem } from './navbar'

// SidebarItem injects this so choosing a navigation entry closes the mobile drawer
// (Headless UI React uses CloseButton for the same job).
export const SidebarCloseContext: InjectionKey<() => void> = Symbol('SidebarCloseContext')

function openMenuIcon() {
  return h(
    'svg',
    { 'data-slot': 'icon', viewBox: '0 0 20 20', 'aria-hidden': 'true' },
    h('path', {
      d: 'M2 6.75C2 6.33579 2.33579 6 2.75 6H17.25C17.6642 6 18 6.33579 18 6.75C18 7.16421 17.6642 7.5 17.25 7.5H2.75C2.33579 7.5 2 7.16421 2 6.75ZM2 13.25C2 12.8358 2.33579 12.5 2.75 12.5H17.25C17.6642 12.5 18 12.8358 18 13.25C18 13.6642 17.6642 14 17.25 14H2.75C2.33579 14 2 13.6642 2 13.25Z',
    }),
  )
}

function closeMenuIcon() {
  return h(
    'svg',
    { 'data-slot': 'icon', viewBox: '0 0 20 20', 'aria-hidden': 'true' },
    h('path', {
      d: 'M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z',
    }),
  )
}

export const StackedLayout = defineComponent({
  name: 'CatalystStackedLayout',
  setup(_, { slots }) {
    const showSidebar = ref(false)
    const close = () => (showSidebar.value = false)
    provide(SidebarCloseContext, close)

    const mobileSidebar = () =>
      h(TransitionRoot, { show: showSidebar.value, as: 'template' }, () =>
        h(HDialog, { as: 'div', class: 'lg:hidden', onClose: close }, () => [
          h(
            TransitionChild,
            {
              as: 'template',
              enter: 'transition duration-300 ease-out',
              enterFrom: 'opacity-0',
              enterTo: 'opacity-100',
              leave: 'transition duration-200 ease-in',
              leaveFrom: 'opacity-100',
              leaveTo: 'opacity-0',
            },
            () => h('div', { class: 'fixed inset-0 bg-black/30' }),
          ),
          h(
            TransitionChild,
            {
              as: 'template',
              enter: 'transition duration-300 ease-in-out',
              enterFrom: '-translate-x-full',
              enterTo: 'translate-x-0',
              leave: 'transition duration-300 ease-in-out',
              leaveFrom: 'translate-x-0',
              leaveTo: '-translate-x-full',
            },
            () =>
              h(
                DialogPanel,
                { class: 'fixed inset-y-0 w-full max-w-80 p-2' },
                () =>
                  h(
                    'div',
                    {
                      class:
                        'flex h-full flex-col rounded-lg bg-white shadow-xs ring-1 ring-zinc-950/5 dark:bg-zinc-900 dark:ring-white/10',
                    },
                    [
                      h(
                        'div',
                        { class: '-mb-3 px-4 pt-3' },
                        h(NavbarItem, { 'aria-label': 'Close navigation', onClick: close }, () => closeMenuIcon()),
                      ),
                      slots.sidebar?.(),
                    ],
                  ),
              ),
          ),
        ]),
      )

    return () =>
      h(
        'div',
        {
          // text-zinc-950/dark:text-white come from <html> in the Catalyst demo app;
          // carried here so the layout is self-contained.
          class:
            'relative isolate flex min-h-svh w-full flex-col bg-white text-zinc-950 lg:bg-zinc-100 dark:bg-zinc-900 dark:text-white dark:lg:bg-zinc-950',
        },
        [
          // Sidebar on mobile
          mobileSidebar(),
          // Navbar
          h('header', { class: 'flex items-center px-4' }, [
            h(
              'div',
              { class: 'py-2.5 lg:hidden' },
              h(NavbarItem, { 'aria-label': 'Open navigation', onClick: () => (showSidebar.value = true) }, () =>
                openMenuIcon(),
              ),
            ),
            h('div', { class: 'min-w-0 flex-1' }, slots.navbar?.()),
          ]),
          // Content
          h(
            'main',
            { class: 'flex flex-1 flex-col pb-2 lg:px-2' },
            h(
              'div',
              {
                class:
                  'grow p-6 lg:rounded-lg lg:bg-white lg:p-10 lg:shadow-xs lg:ring-1 lg:ring-zinc-950/5 dark:lg:bg-zinc-900 dark:lg:ring-white/10',
              },
              h('div', { class: 'mx-auto max-w-6xl' }, slots.default?.()),
            ),
          ),
        ],
      )
  },
})
