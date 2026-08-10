// Vue port of Catalyst's navbar.tsx. The motion/react LayoutGroup animation on the
// current-page indicator is omitted (static span); data-hover/data-active → hover/active.
import { defineComponent, h } from 'vue'
import { touchTarget } from './button'

type Ctx = { slots: any; attrs: any }

export function Navbar(_: unknown, { slots, attrs }: Ctx) {
  return h('nav', { ...attrs, class: [attrs.class, 'flex flex-1 items-center gap-4 py-2.5'] }, slots.default?.())
}

export function NavbarDivider(_: unknown, { attrs }: Ctx) {
  return h('div', { 'aria-hidden': 'true', ...attrs, class: [attrs.class, 'h-6 w-px bg-zinc-950/10 dark:bg-white/10'] })
}

export function NavbarSection(_: unknown, { slots, attrs }: Ctx) {
  return h('div', { ...attrs, class: [attrs.class, 'flex items-center gap-3'] }, slots.default?.())
}

export function NavbarSpacer(_: unknown, { attrs }: Ctx) {
  return h('div', { 'aria-hidden': 'true', ...attrs, class: [attrs.class, '-ml-4 flex-1'] })
}

export const NavbarItem = defineComponent({
  name: 'CatalystNavbarItem',
  inheritAttrs: false,
  props: {
    current: { type: Boolean, default: false },
    href: { type: String, default: undefined },
  },
  setup(props, { slots, attrs }) {
    const classes = [
      // Base
      'relative flex min-w-0 items-center gap-3 rounded-lg p-2 text-left text-base/6 font-medium text-zinc-950 sm:text-sm/5',
      // Leading icon/icon-only
      '*:data-[slot=icon]:size-6 *:data-[slot=icon]:shrink-0 *:data-[slot=icon]:fill-zinc-500 sm:*:data-[slot=icon]:size-5',
      // Trailing icon (down chevron or similar)
      '*:not-nth-2:last:data-[slot=icon]:ml-auto *:not-nth-2:last:data-[slot=icon]:size-5 sm:*:not-nth-2:last:data-[slot=icon]:size-4',
      // Avatar
      '*:data-[slot=avatar]:-m-0.5 *:data-[slot=avatar]:size-7 *:data-[slot=avatar]:[--avatar-radius:var(--radius-md)] sm:*:data-[slot=avatar]:size-6',
      // Hover
      'hover:bg-zinc-950/5 hover:*:data-[slot=icon]:fill-zinc-950',
      // Active
      'active:bg-zinc-950/5 active:*:data-[slot=icon]:fill-zinc-950',
      // Dark mode
      'dark:text-white dark:*:data-[slot=icon]:fill-zinc-400',
      'dark:hover:bg-white/5 dark:hover:*:data-[slot=icon]:fill-white',
      'dark:active:bg-white/5 dark:active:*:data-[slot=icon]:fill-white',
    ]

    return () => {
      const { class: klass, ...rest } = attrs
      const children = [touchTarget(), slots.default?.()]
      const dataCurrent = props.current ? 'true' : undefined
      return h('span', { class: [klass, 'relative'] }, [
        props.current
          ? h('span', { class: 'absolute inset-x-2 -bottom-2.5 h-0.5 rounded-full bg-zinc-950 dark:bg-white' })
          : null,
        typeof props.href === 'string'
          ? h('a', { ...rest, href: props.href, class: classes, 'data-current': dataCurrent }, children)
          : h(
              'button',
              { ...rest, type: 'button', class: ['cursor-default', classes], 'data-current': dataCurrent },
              children,
            ),
      ])
    }
  },
})

export function NavbarLabel(_: unknown, { slots, attrs }: Ctx) {
  return h('span', { ...attrs, class: [attrs.class, 'truncate'] }, slots.default?.())
}
