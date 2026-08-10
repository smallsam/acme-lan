// Vue port of Catalyst's avatar.tsx (Avatar only; the button variant is unused here).
import { defineComponent, h } from 'vue'

export const Avatar = defineComponent({
  name: 'CatalystAvatar',
  props: {
    src: { type: String, default: null },
    square: { type: Boolean, default: false },
    initials: { type: String, default: undefined },
    alt: { type: String, default: '' },
  },
  setup(props, { attrs }) {
    return () =>
      h(
        'span',
        {
          ...attrs,
          'data-slot': 'avatar',
          class: [
            attrs.class,
            // Basic layout
            'inline-grid shrink-0 align-middle [--avatar-radius:20%] *:col-start-1 *:row-start-1',
            'outline -outline-offset-1 outline-black/10 dark:outline-white/10',
            // Border radius
            props.square ? 'rounded-(--avatar-radius) *:rounded-(--avatar-radius)' : 'rounded-full *:rounded-full',
          ],
        },
        [
          props.initials &&
            h(
              'svg',
              {
                class: 'size-full fill-current p-[5%] text-[48px] font-medium uppercase select-none',
                viewBox: '0 0 100 100',
                'aria-hidden': props.alt ? undefined : 'true',
              },
              [
                props.alt ? h('title', props.alt) : null,
                h(
                  'text',
                  {
                    x: '50%',
                    y: '50%',
                    'alignment-baseline': 'middle',
                    'dominant-baseline': 'middle',
                    'text-anchor': 'middle',
                    dy: '.125em',
                  },
                  props.initials,
                ),
              ],
            ),
          props.src && h('img', { class: 'size-full', src: props.src, alt: props.alt }),
        ],
      )
  },
})
