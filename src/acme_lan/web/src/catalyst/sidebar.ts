// Vue port of Catalyst's sidebar.tsx (the subset the stacked layout's mobile drawer
// needs). SidebarItem closes the drawer it lives in via the context StackedLayout
// provides, standing in for Headless UI React's CloseButton.
import { defineComponent, h, inject } from 'vue'
import { touchTarget } from './button'
import { SidebarCloseContext } from './stacked-layout'

type Ctx = { slots: any; attrs: any }

export function Sidebar(_: unknown, { slots, attrs }: Ctx) {
  return h('nav', { ...attrs, class: [attrs.class, 'flex h-full min-h-0 flex-col'] }, slots.default?.())
}

export function SidebarHeader(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'div',
    {
      ...attrs,
      class: [
        attrs.class,
        'flex flex-col border-b border-zinc-950/5 p-4 dark:border-white/5 [&>[data-slot=section]+[data-slot=section]]:mt-2.5',
      ],
    },
    slots.default?.(),
  )
}

export function SidebarBody(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'div',
    {
      ...attrs,
      class: [attrs.class, 'flex flex-1 flex-col overflow-y-auto p-4 [&>[data-slot=section]+[data-slot=section]]:mt-8'],
    },
    slots.default?.(),
  )
}

export function SidebarSection(_: unknown, { slots, attrs }: Ctx) {
  return h('div', { ...attrs, 'data-slot': 'section', class: [attrs.class, 'flex flex-col gap-0.5'] }, slots.default?.())
}

export function SidebarSpacer(_: unknown, { attrs }: Ctx) {
  return h('div', { 'aria-hidden': 'true', ...attrs, class: [attrs.class, 'mt-8 flex-1'] })
}

export function SidebarHeading(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'h3',
    { ...attrs, class: [attrs.class, 'mb-1 px-2 text-xs/6 font-medium text-zinc-500 dark:text-zinc-400'] },
    slots.default?.(),
  )
}

export const SidebarItem = defineComponent({
  name: 'CatalystSidebarItem',
  inheritAttrs: false,
  props: {
    current: { type: Boolean, default: false },
    href: { type: String, default: undefined },
  },
  setup(props, { slots, attrs }) {
    const closeSidebar = inject(SidebarCloseContext, null)
    const classes = [
      // Base
      'flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left text-base/6 font-medium text-zinc-950 sm:py-2 sm:text-sm/5',
      // Leading icon/icon-only
      '*:data-[slot=icon]:size-6 *:data-[slot=icon]:shrink-0 *:data-[slot=icon]:fill-zinc-500 sm:*:data-[slot=icon]:size-5',
      // Trailing icon (down chevron or similar)
      '*:last:data-[slot=icon]:ml-auto *:last:data-[slot=icon]:size-5 sm:*:last:data-[slot=icon]:size-4',
      // Avatar
      '*:data-[slot=avatar]:-m-0.5 *:data-[slot=avatar]:size-7 sm:*:data-[slot=avatar]:size-6',
      // Hover
      'hover:bg-zinc-950/5 hover:*:data-[slot=icon]:fill-zinc-950',
      // Active
      'active:bg-zinc-950/5 active:*:data-[slot=icon]:fill-zinc-950',
      // Current
      'data-current:*:data-[slot=icon]:fill-zinc-950',
      // Dark mode
      'dark:text-white dark:*:data-[slot=icon]:fill-zinc-400',
      'dark:hover:bg-white/5 dark:hover:*:data-[slot=icon]:fill-white',
      'dark:active:bg-white/5 dark:active:*:data-[slot=icon]:fill-white',
      'dark:data-current:*:data-[slot=icon]:fill-white',
    ]

    return () => {
      const { class: klass, onClick, ...rest } = attrs as Record<string, unknown> & {
        onClick?: (event: MouseEvent) => void
      }
      const handleClick = (event: MouseEvent) => {
        onClick?.(event)
        closeSidebar?.()
      }
      const children = [touchTarget(), slots.default?.()]
      const dataCurrent = props.current ? 'true' : undefined
      return h('span', { class: [klass, 'relative'] }, [
        props.current
          ? h('span', { class: 'absolute inset-y-2 -left-4 w-0.5 rounded-full bg-zinc-950 dark:bg-white' })
          : null,
        typeof props.href === 'string'
          ? h('a', { ...rest, href: props.href, onClick: handleClick, class: classes, 'data-current': dataCurrent }, children)
          : h(
              'button',
              {
                ...rest,
                type: 'button',
                onClick: handleClick,
                class: ['cursor-default', classes],
                'data-current': dataCurrent,
              },
              children,
            ),
      ])
    }
  },
})

export function SidebarLabel(_: unknown, { slots, attrs }: Ctx) {
  return h('span', { ...attrs, class: [attrs.class, 'truncate'] }, slots.default?.())
}
