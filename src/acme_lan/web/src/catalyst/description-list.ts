// Vue port of Catalyst's description-list.tsx.
import { h } from 'vue'

type Ctx = { slots: any; attrs: any }

export function DescriptionList(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'dl',
    {
      ...attrs,
      class: [attrs.class, 'grid grid-cols-1 text-base/6 sm:grid-cols-[min(50%,--spacing(80))_auto] sm:text-sm/6'],
    },
    slots.default?.(),
  )
}

export function DescriptionTerm(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'dt',
    {
      ...attrs,
      class: [
        attrs.class,
        'col-start-1 border-t border-zinc-950/5 pt-3 text-zinc-500 first:border-none sm:border-t sm:border-zinc-950/5 sm:py-3 dark:border-white/5 dark:text-zinc-400 sm:dark:border-white/5',
      ],
    },
    slots.default?.(),
  )
}

export function DescriptionDetails(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'dd',
    {
      ...attrs,
      class: [
        attrs.class,
        'pt-1 pb-3 text-zinc-950 sm:border-t sm:border-zinc-950/5 sm:py-3 sm:nth-2:border-none dark:text-white dark:sm:border-white/5',
      ],
    },
    slots.default?.(),
  )
}
