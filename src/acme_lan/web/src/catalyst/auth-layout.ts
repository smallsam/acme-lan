// Vue port of Catalyst's auth-layout.tsx, with the page background the demo puts on
// <body> folded into the root so the login screen matches the stacked layout's frame.
import { h } from 'vue'

export function AuthLayout(_: unknown, { slots, attrs }: { slots: any; attrs: any }) {
  return h(
    'main',
    {
      ...attrs,
      class: [
        attrs.class,
        'flex min-h-dvh flex-col p-2 bg-white text-zinc-950 lg:bg-zinc-100 dark:bg-zinc-900 dark:text-white dark:lg:bg-zinc-950',
      ],
    },
    h(
      'div',
      {
        class:
          'flex grow items-center justify-center p-6 lg:rounded-lg lg:bg-white lg:p-10 lg:shadow-xs lg:ring-1 lg:ring-zinc-950/5 dark:lg:bg-zinc-900 dark:lg:ring-white/10',
      },
      slots.default?.(),
    ),
  )
}
