// Not part of Catalyst (its alert.tsx is a modal): an inline banner for error/success
// messages, composed from the same color recipe as badge.ts so it reads as one system.
import { defineComponent, h, type PropType } from 'vue'

const colors = {
  red: 'bg-red-500/15 text-red-700 dark:bg-red-500/10 dark:text-red-400',
  green: 'bg-green-500/15 text-green-700 dark:bg-green-500/10 dark:text-green-400',
  amber: 'bg-amber-400/20 text-amber-700 dark:bg-amber-400/10 dark:text-amber-400',
  blue: 'bg-blue-500/15 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400',
  zinc: 'bg-zinc-600/10 text-zinc-700 dark:bg-white/5 dark:text-zinc-400',
}

export type NoticeColor = keyof typeof colors

export const Notice = defineComponent({
  name: 'CatalystNotice',
  props: { color: { type: String as PropType<NoticeColor>, default: 'zinc' } },
  setup(props, { slots, attrs }) {
    return () =>
      h(
        'div',
        { ...attrs, class: [attrs.class, 'rounded-lg px-4 py-3 text-base/6 sm:text-sm/6', colors[props.color]] },
        slots.default?.(),
      )
  },
})
