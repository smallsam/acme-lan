// Vue port of Catalyst's text.tsx (data-hover → hover on TextLink).
import { h } from 'vue'

type Ctx = { slots: any; attrs: any }

export function Text(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'p',
    { ...attrs, 'data-slot': 'text', class: [attrs.class, 'text-base/6 text-zinc-500 sm:text-sm/6 dark:text-zinc-400'] },
    slots.default?.(),
  )
}

export function TextLink(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'a',
    {
      ...attrs,
      class: [
        attrs.class,
        'text-zinc-950 underline decoration-zinc-950/50 hover:decoration-zinc-950 dark:text-white dark:decoration-white/50 dark:hover:decoration-white',
      ],
    },
    slots.default?.(),
  )
}

export function Strong(_: unknown, { slots, attrs }: Ctx) {
  return h('strong', { ...attrs, class: [attrs.class, 'font-medium text-zinc-950 dark:text-white'] }, slots.default?.())
}

export function Code(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'code',
    {
      ...attrs,
      class: [
        attrs.class,
        'rounded-sm border border-zinc-950/10 bg-zinc-950/2.5 px-0.5 text-sm font-medium text-zinc-950 sm:text-[0.8125rem] dark:border-white/20 dark:bg-white/5 dark:text-white',
      ],
    },
    slots.default?.(),
  )
}
