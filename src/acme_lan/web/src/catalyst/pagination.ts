// Vue port of Catalyst's pagination.tsx. This SPA pages client-side, so the href-based
// API becomes disabled/current props plus click events (buttons instead of links).
import { defineComponent, h } from 'vue'
import { Button } from './button'

type Ctx = { slots: any; attrs: any }

export function Pagination(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'nav',
    { 'aria-label': 'Page navigation', ...attrs, class: [attrs.class, 'flex gap-x-2'] },
    slots.default?.(),
  )
}

function arrow(direction: 'previous' | 'next') {
  return h(
    'svg',
    { class: 'stroke-current', 'data-slot': 'icon', viewBox: '0 0 16 16', fill: 'none', 'aria-hidden': 'true' },
    h('path', {
      d:
        direction === 'previous'
          ? 'M2.75 8H13.25M2.75 8L5.25 5.5M2.75 8L5.25 10.5'
          : 'M13.25 8L2.75 8M13.25 8L10.75 10.5M13.25 8L10.75 5.5',
      'stroke-width': '1.5',
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
    }),
  )
}

export const PaginationPrevious = defineComponent({
  name: 'CatalystPaginationPrevious',
  inheritAttrs: false,
  props: { disabled: { type: Boolean, default: false } },
  setup(props, { slots, attrs }) {
    const { class: klass, ...rest } = attrs
    return () =>
      h(
        'span',
        { class: [klass, 'grow basis-0'] },
        h(Button, { ...rest, plain: true, disabled: props.disabled, 'aria-label': 'Previous page' }, () => [
          arrow('previous'),
          slots.default ? slots.default() : 'Previous',
        ]),
      )
  },
})

export const PaginationNext = defineComponent({
  name: 'CatalystPaginationNext',
  inheritAttrs: false,
  props: { disabled: { type: Boolean, default: false } },
  setup(props, { slots, attrs }) {
    const { class: klass, ...rest } = attrs
    return () =>
      h(
        'span',
        { class: [klass, 'flex grow basis-0 justify-end'] },
        h(Button, { ...rest, plain: true, disabled: props.disabled, 'aria-label': 'Next page' }, () => [
          slots.default ? slots.default() : 'Next',
          arrow('next'),
        ]),
      )
  },
})

export function PaginationList(_: unknown, { slots, attrs }: Ctx) {
  return h('span', { ...attrs, class: [attrs.class, 'hidden items-baseline gap-x-2 sm:flex'] }, slots.default?.())
}

export const PaginationPage = defineComponent({
  name: 'CatalystPaginationPage',
  inheritAttrs: false,
  props: { current: { type: Boolean, default: false } },
  setup(props, { slots, attrs }) {
    return () => {
      const { class: klass, ...rest } = attrs
      return h(
        Button,
        {
          ...rest,
          plain: true,
          'aria-current': props.current ? 'page' : undefined,
          class: [
            klass,
            'min-w-9 before:absolute before:-inset-px before:rounded-lg',
            props.current && 'before:bg-zinc-950/5 dark:before:bg-white/10',
          ],
        },
        () => h('span', { class: '-mx-0.5' }, slots.default?.()),
      )
    }
  },
})

export function PaginationGap(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'span',
    {
      'aria-hidden': 'true',
      ...attrs,
      class: [attrs.class, 'w-9 text-center text-sm/6 font-semibold text-zinc-950 select-none dark:text-white'],
    },
    slots.default ? slots.default() : '…',
  )
}
