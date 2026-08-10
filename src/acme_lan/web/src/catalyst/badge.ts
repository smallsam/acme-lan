// Vue port of Catalyst's badge.tsx (group-data-hover → group-hover).
import { defineComponent, h, type PropType } from 'vue'

export const badgeColors = {
  red: 'bg-red-500/15 text-red-700 group-hover:bg-red-500/25 dark:bg-red-500/10 dark:text-red-400 dark:group-hover:bg-red-500/20',
  orange:
    'bg-orange-500/15 text-orange-700 group-hover:bg-orange-500/25 dark:bg-orange-500/10 dark:text-orange-400 dark:group-hover:bg-orange-500/20',
  amber:
    'bg-amber-400/20 text-amber-700 group-hover:bg-amber-400/30 dark:bg-amber-400/10 dark:text-amber-400 dark:group-hover:bg-amber-400/15',
  yellow:
    'bg-yellow-400/20 text-yellow-700 group-hover:bg-yellow-400/30 dark:bg-yellow-400/10 dark:text-yellow-300 dark:group-hover:bg-yellow-400/15',
  lime: 'bg-lime-400/20 text-lime-700 group-hover:bg-lime-400/30 dark:bg-lime-400/10 dark:text-lime-300 dark:group-hover:bg-lime-400/15',
  green:
    'bg-green-500/15 text-green-700 group-hover:bg-green-500/25 dark:bg-green-500/10 dark:text-green-400 dark:group-hover:bg-green-500/20',
  emerald:
    'bg-emerald-500/15 text-emerald-700 group-hover:bg-emerald-500/25 dark:bg-emerald-500/10 dark:text-emerald-400 dark:group-hover:bg-emerald-500/20',
  teal: 'bg-teal-500/15 text-teal-700 group-hover:bg-teal-500/25 dark:bg-teal-500/10 dark:text-teal-300 dark:group-hover:bg-teal-500/20',
  cyan: 'bg-cyan-400/20 text-cyan-700 group-hover:bg-cyan-400/30 dark:bg-cyan-400/10 dark:text-cyan-300 dark:group-hover:bg-cyan-400/15',
  sky: 'bg-sky-500/15 text-sky-700 group-hover:bg-sky-500/25 dark:bg-sky-500/10 dark:text-sky-300 dark:group-hover:bg-sky-500/20',
  blue: 'bg-blue-500/15 text-blue-700 group-hover:bg-blue-500/25 dark:text-blue-400 dark:group-hover:bg-blue-500/25',
  indigo:
    'bg-indigo-500/15 text-indigo-700 group-hover:bg-indigo-500/25 dark:text-indigo-400 dark:group-hover:bg-indigo-500/20',
  violet:
    'bg-violet-500/15 text-violet-700 group-hover:bg-violet-500/25 dark:text-violet-400 dark:group-hover:bg-violet-500/20',
  purple:
    'bg-purple-500/15 text-purple-700 group-hover:bg-purple-500/25 dark:text-purple-400 dark:group-hover:bg-purple-500/20',
  fuchsia:
    'bg-fuchsia-400/15 text-fuchsia-700 group-hover:bg-fuchsia-400/25 dark:bg-fuchsia-400/10 dark:text-fuchsia-400 dark:group-hover:bg-fuchsia-400/20',
  pink: 'bg-pink-400/15 text-pink-700 group-hover:bg-pink-400/25 dark:bg-pink-400/10 dark:text-pink-400 dark:group-hover:bg-pink-400/20',
  rose: 'bg-rose-400/15 text-rose-700 group-hover:bg-rose-400/25 dark:bg-rose-400/10 dark:text-rose-400 dark:group-hover:bg-rose-400/20',
  zinc: 'bg-zinc-600/10 text-zinc-700 group-hover:bg-zinc-600/20 dark:bg-white/5 dark:text-zinc-400 dark:group-hover:bg-white/10',
}

export type BadgeColor = keyof typeof badgeColors

export const Badge = defineComponent({
  name: 'CatalystBadge',
  props: { color: { type: String as PropType<BadgeColor>, default: 'zinc' } },
  setup(props, { slots, attrs }) {
    return () =>
      h(
        'span',
        {
          ...attrs,
          class: [
            attrs.class,
            'inline-flex items-center gap-x-1.5 rounded-md px-1.5 py-0.5 text-sm/5 font-medium sm:text-xs/5 forced-colors:outline',
            badgeColors[props.color],
          ],
        },
        slots.default?.(),
      )
  },
})

// BadgeButton from badge.tsx: a clickable badge (used for the check-port chip).
export const BadgeButton = defineComponent({
  name: 'CatalystBadgeButton',
  inheritAttrs: false,
  props: {
    color: { type: String as PropType<BadgeColor>, default: 'zinc' },
    href: { type: String, default: undefined },
  },
  setup(props, { slots, attrs }) {
    return () => {
      const { class: klass, ...rest } = attrs
      const classes = [
        klass,
        'group relative inline-flex rounded-md focus:outline-hidden focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500',
      ]
      const badge = h(Badge, { color: props.color }, () => slots.default?.())
      return typeof props.href === 'string'
        ? h('a', { ...rest, href: props.href, class: classes }, badge)
        : h('button', { ...rest, type: 'button', class: classes }, badge)
    }
  },
})
