// Vue port of Catalyst's dropdown.tsx on @headlessui/vue's Menu.
//
// Headless UI React v2 anchors MenuItems to the button via floating-ui portals; the Vue
// build has no anchor API, so DropdownMenu reimplements it: items render through a
// Portal with position:fixed, placed from the button's bounding box (same gap/offset as
// Catalyst's --anchor-* variables) so menus escape overflow containers like tables.
// Menu item focus/disabled state is exposed by binding data-focus / data-disabled, which
// keeps Catalyst's class strings verbatim.
import { defineComponent, h, nextTick, onBeforeUnmount, ref, Transition, type PropType } from 'vue'
import { Menu, MenuButton, MenuItem, MenuItems, Portal } from '@headlessui/vue'
import { Button } from './button'

export const Dropdown = defineComponent({
  name: 'CatalystDropdown',
  setup(_, { slots, attrs }) {
    return () => h(Menu, attrs, slots)
  },
})

export const DropdownButton = defineComponent({
  name: 'CatalystDropdownButton',
  inheritAttrs: false,
  props: {
    as: { type: [Object, Function, String] as PropType<any>, default: () => Button },
  },
  setup(props, { slots, attrs }) {
    return () => h(MenuButton, { as: props.as, ...attrs }, slots)
  },
})

type Anchor = 'bottom' | 'bottom start' | 'bottom end' | 'top' | 'top start' | 'top end'

export const DropdownMenu = defineComponent({
  name: 'CatalystDropdownMenu',
  inheritAttrs: false,
  props: { anchor: { type: String as PropType<Anchor>, default: 'bottom' } },
  setup(props, { slots, attrs }) {
    const menu = ref<HTMLElement | null>(null)
    const style = ref<Record<string, string>>({ position: 'fixed', top: '0px', left: '0px', visibility: 'hidden' })

    // Headless UI labels the menu with its button's id, which is the most reliable way
    // back to the anchor element from a portalled menu.
    function anchorButton(el: HTMLElement): HTMLElement | null {
      const labelledBy = el.getAttribute('aria-labelledby')
      return labelledBy ? document.getElementById(labelledBy.split(' ')[0]) : null
    }

    function reposition() {
      const el = menu.value
      if (!el) return
      const button = anchorButton(el)
      if (!button) return
      const rect = button.getBoundingClientRect()
      const gap = 8 // --anchor-gap: --spacing(2)
      const offset = 4 // sm: --anchor-offset on start/end anchors
      const padding = 4 // --anchor-padding: --spacing(1)
      const [side, align] = props.anchor.split(' ')
      let top = side === 'top' ? rect.top - gap - el.offsetHeight : rect.bottom + gap
      let left =
        align === 'start'
          ? rect.left - offset
          : align === 'end'
            ? rect.right - el.offsetWidth + offset
            : rect.left + rect.width / 2 - el.offsetWidth / 2
      left = Math.min(Math.max(padding, left), window.innerWidth - el.offsetWidth - padding)
      top = Math.min(Math.max(padding, top), window.innerHeight - el.offsetHeight - padding)
      const next = {
        position: 'fixed',
        top: `${Math.round(top)}px`,
        left: `${Math.round(left)}px`,
        visibility: 'visible',
      }
      const current = style.value
      // Write only on change: this runs from a vnode ref on every patch, and writing a
      // fresh object each time would re-render (and so re-patch) forever.
      if (current.top !== next.top || current.left !== next.left || current.visibility !== next.visibility) {
        style.value = next
      }
    }

    let listening = false
    function stopListening() {
      if (!listening) return
      window.removeEventListener('resize', reposition)
      window.removeEventListener('scroll', reposition, true)
      listening = false
    }
    function setMenu(instance: any) {
      const el = instance?.$el ?? instance
      menu.value = el instanceof HTMLElement ? el : null
      if (menu.value) {
        nextTick(reposition)
        if (!listening) {
          window.addEventListener('resize', reposition)
          window.addEventListener('scroll', reposition, true)
          listening = true
        }
      } else {
        // Park the next open off-screen until it has been measured and placed. Only write
        // when needed: this runs from a vnode ref on every patch, and an unconditional
        // write would re-render (and so re-patch) forever.
        if (style.value.visibility !== 'hidden') {
          style.value = { position: 'fixed', top: '0px', left: '0px', visibility: 'hidden' }
        }
        stopListening()
      }
    }
    onBeforeUnmount(stopListening)

    return () => {
      const { class: klass, ...rest } = attrs
      return h(Portal, () =>
        h(
          Transition,
          { leaveActiveClass: 'transition duration-100 ease-in', leaveToClass: 'opacity-0' },
          () =>
            h(
              MenuItems,
              {
                ...rest,
                ref: setMenu,
                style: style.value,
                class: [
                  klass,
                  // Base styles
                  'isolate w-max rounded-xl p-1',
                  // Invisible border that is only visible in `forced-colors` mode for accessibility purposes
                  'outline outline-transparent focus:outline-hidden',
                  // Handle scrolling when menu won't fit in viewport
                  'overflow-y-auto',
                  // Popover background
                  'bg-white/75 backdrop-blur-xl dark:bg-zinc-800/75',
                  // Shadows
                  'shadow-lg ring-1 ring-zinc-950/10 dark:ring-white/10 dark:ring-inset',
                  // Define grid at the menu level if subgrid is supported
                  'supports-[grid-template-columns:subgrid]:grid supports-[grid-template-columns:subgrid]:grid-cols-[auto_1fr_1.5rem_0.5rem_auto]',
                ],
              },
              slots,
            ),
        ),
      )
    }
  },
})

export const DropdownItem = defineComponent({
  name: 'CatalystDropdownItem',
  inheritAttrs: false,
  props: {
    href: { type: String, default: undefined },
    disabled: { type: Boolean, default: false },
  },
  setup(props, { slots, attrs }) {
    return () => {
      const { class: klass, ...rest } = attrs
      const classes = [
        klass,
        // Base styles
        'group cursor-default rounded-lg px-3.5 py-2.5 focus:outline-hidden sm:px-3 sm:py-1.5',
        // Text styles
        'text-left text-base/6 text-zinc-950 sm:text-sm/6 dark:text-white forced-colors:text-[CanvasText]',
        // Focus
        'data-focus:bg-blue-500 data-focus:text-white',
        // Disabled state
        'data-disabled:opacity-50',
        // Forced colors mode
        'forced-color-adjust-none forced-colors:data-focus:bg-[Highlight] forced-colors:data-focus:text-[HighlightText] forced-colors:data-focus:*:data-[slot=icon]:text-[HighlightText]',
        // Use subgrid when available but fallback to an explicit grid layout if not
        'col-span-full grid grid-cols-[auto_1fr_1.5rem_0.5rem_auto] items-center supports-[grid-template-columns:subgrid]:grid-cols-subgrid',
        // Icons
        '*:data-[slot=icon]:col-start-1 *:data-[slot=icon]:row-start-1 *:data-[slot=icon]:mr-2.5 *:data-[slot=icon]:-ml-0.5 *:data-[slot=icon]:size-5 sm:*:data-[slot=icon]:mr-2 sm:*:data-[slot=icon]:size-4',
        '*:data-[slot=icon]:text-zinc-500 data-focus:*:data-[slot=icon]:text-white dark:*:data-[slot=icon]:text-zinc-400 dark:data-focus:*:data-[slot=icon]:text-white',
        // Avatar
        '*:data-[slot=avatar]:mr-2.5 *:data-[slot=avatar]:-ml-1 *:data-[slot=avatar]:size-6 sm:*:data-[slot=avatar]:mr-2 sm:*:data-[slot=avatar]:size-5',
      ]
      return h(
        MenuItem,
        { as: 'template', disabled: props.disabled },
        {
          default: ({ active, disabled }: { active: boolean; disabled: boolean }) =>
            typeof props.href === 'string'
              ? h(
                  'a',
                  {
                    ...rest,
                    href: props.href,
                    class: classes,
                    'data-focus': active ? '' : undefined,
                    'data-disabled': disabled ? '' : undefined,
                  },
                  slots.default?.(),
                )
              : h(
                  'button',
                  {
                    ...rest,
                    type: 'button',
                    class: classes,
                    'data-focus': active ? '' : undefined,
                    'data-disabled': disabled ? '' : undefined,
                  },
                  slots.default?.(),
                ),
        },
      )
    }
  },
})

type Ctx = { slots: any; attrs: any }

export function DropdownHeader(_: unknown, { slots, attrs }: Ctx) {
  return h('div', { ...attrs, class: [attrs.class, 'col-span-5 px-3.5 pt-2.5 pb-1 sm:px-3'] }, slots.default?.())
}

export function DropdownHeading(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'header',
    {
      ...attrs,
      class: [
        attrs.class,
        'col-span-full grid grid-cols-[1fr_auto] gap-x-12 px-3.5 pt-2 pb-1 text-sm/5 font-medium text-zinc-500 sm:px-3 sm:text-xs/5 dark:text-zinc-400',
      ],
    },
    slots.default?.(),
  )
}

export function DropdownDivider(_: unknown, { attrs }: Ctx) {
  return h('hr', {
    role: 'separator',
    ...attrs,
    class: [
      attrs.class,
      'col-span-full mx-3.5 my-1 h-px border-0 bg-zinc-950/5 sm:mx-3 dark:bg-white/10 forced-colors:bg-[CanvasText]',
    ],
  })
}

export function DropdownLabel(_: unknown, { slots, attrs }: Ctx) {
  return h('div', { ...attrs, 'data-slot': 'label', class: [attrs.class, 'col-start-2 row-start-1'] }, slots.default?.())
}

export function DropdownDescription(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'div',
    {
      ...attrs,
      'data-slot': 'description',
      class: [
        attrs.class,
        'col-span-2 col-start-2 row-start-2 text-sm/5 text-zinc-500 group-data-focus:text-white sm:text-xs/5 dark:text-zinc-400 forced-colors:group-data-focus:text-[HighlightText]',
      ],
    },
    slots.default?.(),
  )
}
