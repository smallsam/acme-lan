// Vue port of Catalyst's fieldset.tsx. Field renders a <label> (and Label a <span>) so
// the caption/control association comes from nesting instead of Headless UI's id wiring.
import { h } from 'vue'

type Ctx = { slots: any; attrs: any }

export function Fieldset(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'fieldset',
    { ...attrs, class: [attrs.class, '*:data-[slot=text]:mt-1 [&>*+[data-slot=control]]:mt-6'] },
    slots.default?.(),
  )
}

export function Legend(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'legend',
    {
      ...attrs,
      'data-slot': 'legend',
      class: [attrs.class, 'text-base/6 font-semibold text-zinc-950 sm:text-sm/6 dark:text-white'],
    },
    slots.default?.(),
  )
}

export function FieldGroup(_: unknown, { slots, attrs }: Ctx) {
  return h('div', { ...attrs, 'data-slot': 'control', class: [attrs.class, 'space-y-8'] }, slots.default?.())
}

export function Field(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'label',
    {
      ...attrs,
      class: [
        attrs.class,
        'block',
        '[&>[data-slot=label]+[data-slot=control]]:mt-3',
        '[&>[data-slot=label]+[data-slot=description]]:mt-1',
        '[&>[data-slot=description]+[data-slot=control]]:mt-3',
        '[&>[data-slot=control]+[data-slot=description]]:mt-3',
        '[&>[data-slot=control]+[data-slot=error]]:mt-3',
        '*:data-[slot=label]:font-medium',
      ],
    },
    slots.default?.(),
  )
}

export function Label(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'span',
    {
      ...attrs,
      'data-slot': 'label',
      class: [attrs.class, 'block text-base/6 text-zinc-950 select-none sm:text-sm/6 dark:text-white'],
    },
    slots.default?.(),
  )
}

export function Description(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'p',
    {
      ...attrs,
      'data-slot': 'description',
      class: [attrs.class, 'text-base/6 text-zinc-500 sm:text-sm/6 dark:text-zinc-400'],
    },
    slots.default?.(),
  )
}

export function ErrorMessage(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'p',
    {
      ...attrs,
      'data-slot': 'error',
      class: [attrs.class, 'text-base/6 text-red-600 sm:text-sm/6 dark:text-red-500'],
    },
    slots.default?.(),
  )
}
