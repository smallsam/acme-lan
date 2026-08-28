// Vue port of Catalyst's divider.tsx.
import { defineComponent, h } from 'vue'

export const Divider = defineComponent({
  name: 'CatalystDivider',
  props: { soft: { type: Boolean, default: false } },
  setup(props, { attrs }) {
    return () =>
      h('hr', {
        role: 'presentation',
        ...attrs,
        class: [
          attrs.class,
          'w-full border-t',
          props.soft ? 'border-zinc-950/5 dark:border-white/5' : 'border-zinc-950/10 dark:border-white/10',
        ],
      })
  },
})
