// Vue port of Catalyst's checkbox.tsx. The visual box is Catalyst's markup verbatim;
// interaction comes from an invisible native <input type="checkbox"> stretched over it,
// with data-checked / data-disabled bound on the group so the original group-data-*
// selectors apply unchanged (group-data-hover → group-hover, group-data-focus →
// peer-focus-visible on the box, which sits after the input).
import { defineComponent, h, type PropType } from 'vue'

export function CheckboxGroup(_: unknown, { slots, attrs }: { slots: any; attrs: any }) {
  return h(
    'div',
    {
      ...attrs,
      'data-slot': 'control',
      class: [
        attrs.class,
        // Basic groups
        'space-y-3',
        // With descriptions
        'has-data-[slot=description]:space-y-6 has-data-[slot=description]:**:data-[slot=label]:font-medium',
      ],
    },
    slots.default?.(),
  )
}

// A <label> element so clicking the text toggles the checkbox inside it.
export function CheckboxField(_: unknown, { slots, attrs }: { slots: any; attrs: any }) {
  return h(
    'label',
    {
      ...attrs,
      'data-slot': 'field',
      class: [
        attrs.class,
        // Base layout
        'grid grid-cols-[1.125rem_1fr] gap-x-4 gap-y-1 sm:grid-cols-[1rem_1fr]',
        // Control layout
        '*:data-[slot=control]:col-start-1 *:data-[slot=control]:row-start-1 *:data-[slot=control]:mt-0.75 sm:*:data-[slot=control]:mt-1',
        // Label layout
        '*:data-[slot=label]:col-start-2 *:data-[slot=label]:row-start-1',
        // Description layout
        '*:data-[slot=description]:col-start-2 *:data-[slot=description]:row-start-2',
        // With description
        'has-data-[slot=description]:**:data-[slot=label]:font-medium',
      ],
    },
    slots.default?.(),
  )
}

const base = [
  // Basic layout
  'relative isolate flex size-4.5 items-center justify-center rounded-[0.3125rem] sm:size-4',
  // Background color + shadow applied to inset pseudo element, so shadow blends with border in light mode
  'before:absolute before:inset-0 before:-z-10 before:rounded-[calc(0.3125rem-1px)] before:bg-white before:shadow-sm',
  // Background color when checked
  'group-data-checked:before:bg-(--checkbox-checked-bg)',
  // Background color is moved to control and shadow is removed in dark mode so hide `before` pseudo
  'dark:before:hidden',
  // Background color applied to control in dark mode
  'dark:bg-white/5 dark:group-data-checked:bg-(--checkbox-checked-bg)',
  // Border
  'border border-zinc-950/15 group-data-checked:border-transparent group-hover:group-data-checked:border-transparent group-hover:border-zinc-950/30 group-data-checked:bg-(--checkbox-checked-border)',
  'dark:border-white/15 dark:group-data-checked:border-white/5 dark:group-hover:group-data-checked:border-white/5 dark:group-hover:border-white/30',
  // Inner highlight shadow
  'after:absolute after:inset-0 after:rounded-[calc(0.3125rem-1px)] after:shadow-[inset_0_1px_--theme(--color-white/15%)]',
  'dark:after:-inset-px dark:after:hidden dark:after:rounded-[0.3125rem] dark:group-data-checked:after:block',
  // Focus ring
  'peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-blue-500',
  // Disabled state
  'group-data-disabled:opacity-50',
  'group-data-disabled:border-zinc-950/25 group-data-disabled:bg-zinc-950/5 group-data-disabled:[--checkbox-check:var(--color-zinc-950)]/50 group-data-disabled:before:bg-transparent',
  'dark:group-data-disabled:border-white/20 dark:group-data-disabled:bg-white/2.5 dark:group-data-disabled:[--checkbox-check:var(--color-white)]/50 dark:group-data-checked:group-data-disabled:after:hidden',
  // Forced colors mode
  'forced-colors:[--checkbox-check:HighlightText] forced-colors:[--checkbox-checked-bg:Highlight] forced-colors:group-data-disabled:[--checkbox-check:Highlight]',
  'dark:forced-colors:[--checkbox-check:HighlightText] dark:forced-colors:[--checkbox-checked-bg:Highlight] dark:forced-colors:group-data-disabled:[--checkbox-check:Highlight]',
]

const colors = {
  'dark/zinc': [
    '[--checkbox-check:var(--color-white)] [--checkbox-checked-bg:var(--color-zinc-900)] [--checkbox-checked-border:var(--color-zinc-950)]/90',
    'dark:[--checkbox-checked-bg:var(--color-zinc-600)]',
  ],
  'dark/white': [
    '[--checkbox-check:var(--color-white)] [--checkbox-checked-bg:var(--color-zinc-900)] [--checkbox-checked-border:var(--color-zinc-950)]/90',
    'dark:[--checkbox-check:var(--color-zinc-900)] dark:[--checkbox-checked-bg:var(--color-white)] dark:[--checkbox-checked-border:var(--color-zinc-950)]/15',
  ],
  white:
    '[--checkbox-check:var(--color-zinc-900)] [--checkbox-checked-bg:var(--color-white)] [--checkbox-checked-border:var(--color-zinc-950)]/15',
  dark: '[--checkbox-check:var(--color-white)] [--checkbox-checked-bg:var(--color-zinc-900)] [--checkbox-checked-border:var(--color-zinc-950)]/90',
  zinc: '[--checkbox-check:var(--color-white)] [--checkbox-checked-bg:var(--color-zinc-600)] [--checkbox-checked-border:var(--color-zinc-700)]/90',
  red: '[--checkbox-check:var(--color-white)] [--checkbox-checked-bg:var(--color-red-600)] [--checkbox-checked-border:var(--color-red-700)]/90',
  amber:
    '[--checkbox-check:var(--color-amber-950)] [--checkbox-checked-bg:var(--color-amber-400)] [--checkbox-checked-border:var(--color-amber-500)]/80',
  green:
    '[--checkbox-check:var(--color-white)] [--checkbox-checked-bg:var(--color-green-600)] [--checkbox-checked-border:var(--color-green-700)]/90',
  sky: '[--checkbox-check:var(--color-white)] [--checkbox-checked-bg:var(--color-sky-500)] [--checkbox-checked-border:var(--color-sky-600)]/80',
  blue: '[--checkbox-check:var(--color-white)] [--checkbox-checked-bg:var(--color-blue-600)] [--checkbox-checked-border:var(--color-blue-700)]/90',
  indigo:
    '[--checkbox-check:var(--color-white)] [--checkbox-checked-bg:var(--color-indigo-500)] [--checkbox-checked-border:var(--color-indigo-600)]/90',
  violet:
    '[--checkbox-check:var(--color-white)] [--checkbox-checked-bg:var(--color-violet-500)] [--checkbox-checked-border:var(--color-violet-600)]/90',
}

export type CheckboxColor = keyof typeof colors

export const Checkbox = defineComponent({
  name: 'CatalystCheckbox',
  inheritAttrs: false,
  props: {
    modelValue: { type: Boolean, default: false },
    color: { type: String as PropType<CheckboxColor>, default: 'dark/zinc' },
    disabled: { type: Boolean, default: false },
    indeterminate: { type: Boolean, default: false },
  },
  emits: ['update:modelValue'],
  setup(props, { attrs, emit }) {
    return () => {
      const { class: klass, ...rest } = attrs
      return h(
        'span',
        {
          'data-slot': 'control',
          'data-checked': props.modelValue ? '' : undefined,
          'data-disabled': props.disabled ? '' : undefined,
          'data-indeterminate': props.indeterminate ? '' : undefined,
          class: [klass, 'group relative inline-flex focus:outline-hidden'],
        },
        [
          h('input', {
            ...rest,
            type: 'checkbox',
            checked: props.modelValue,
            disabled: props.disabled,
            '.indeterminate': props.indeterminate,
            class: 'peer absolute inset-0 z-10 appearance-none opacity-0',
            onChange: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).checked),
          }),
          h('span', { class: [base, colors[props.color]] }, [
            h(
              'svg',
              {
                class:
                  'size-4 stroke-(--checkbox-check) opacity-0 group-data-checked:opacity-100 sm:h-3.5 sm:w-3.5',
                viewBox: '0 0 14 14',
                fill: 'none',
              },
              [
                // Checkmark icon
                h('path', {
                  class: 'opacity-100 group-data-indeterminate:opacity-0',
                  d: 'M3 8L6 11L11 3.5',
                  'stroke-width': '2',
                  'stroke-linecap': 'round',
                  'stroke-linejoin': 'round',
                }),
                // Indeterminate icon
                h('path', {
                  class: 'opacity-0 group-data-indeterminate:opacity-100',
                  d: 'M3 7H11',
                  'stroke-width': '2',
                  'stroke-linecap': 'round',
                  'stroke-linejoin': 'round',
                }),
              ],
            ),
          ]),
        ],
      )
    }
  },
})
