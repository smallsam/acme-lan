// Vue port of Catalyst's heading.tsx.
import { defineComponent, h, type PropType } from 'vue'

export const Heading = defineComponent({
  name: 'CatalystHeading',
  props: { level: { type: Number as PropType<1 | 2 | 3 | 4 | 5 | 6>, default: 1 } },
  setup(props, { slots, attrs }) {
    return () =>
      h(
        `h${props.level}`,
        { ...attrs, class: [attrs.class, 'text-2xl/8 font-semibold text-zinc-950 sm:text-xl/8 dark:text-white'] },
        slots.default?.(),
      )
  },
})

export const Subheading = defineComponent({
  name: 'CatalystSubheading',
  props: { level: { type: Number as PropType<1 | 2 | 3 | 4 | 5 | 6>, default: 2 } },
  setup(props, { slots, attrs }) {
    return () =>
      h(
        `h${props.level}`,
        { ...attrs, class: [attrs.class, 'text-base/7 font-semibold text-zinc-950 sm:text-sm/6 dark:text-white'] },
        slots.default?.(),
      )
  },
})
