// Vue port of Catalyst's dialog.tsx on @headlessui/vue's Dialog. The React data-closed
// transition utilities become TransitionRoot/TransitionChild enter/leave classes.
import { defineComponent, h, type PropType } from 'vue'
import {
  Dialog as HDialog,
  DialogDescription as HDialogDescription,
  DialogPanel,
  DialogTitle as HDialogTitle,
  TransitionChild,
  TransitionRoot,
} from '@headlessui/vue'

const sizes = {
  xs: 'sm:max-w-xs',
  sm: 'sm:max-w-sm',
  md: 'sm:max-w-md',
  lg: 'sm:max-w-lg',
  xl: 'sm:max-w-xl',
  '2xl': 'sm:max-w-2xl',
  '3xl': 'sm:max-w-3xl',
  '4xl': 'sm:max-w-4xl',
  '5xl': 'sm:max-w-5xl',
}

export const Dialog = defineComponent({
  name: 'CatalystDialog',
  inheritAttrs: false,
  props: {
    open: { type: Boolean, required: true },
    size: { type: String as PropType<keyof typeof sizes>, default: 'lg' },
  },
  emits: ['close'],
  setup(props, { slots, attrs, emit }) {
    return () => {
      const { class: klass, ...rest } = attrs
      return h(TransitionRoot, { show: props.open, as: 'template', appear: true }, () =>
        h(HDialog, { as: 'div', onClose: () => emit('close') }, () => [
          h(
            TransitionChild,
            {
              as: 'template',
              enter: 'transition duration-100 ease-out',
              enterFrom: 'opacity-0',
              enterTo: 'opacity-100',
              leave: 'transition duration-100 ease-in',
              leaveFrom: 'opacity-100',
              leaveTo: 'opacity-0',
            },
            () =>
              h('div', {
                class:
                  'fixed inset-0 flex w-screen justify-center overflow-y-auto bg-zinc-950/25 px-2 py-2 focus:outline-0 sm:px-6 sm:py-8 lg:px-8 lg:py-16 dark:bg-zinc-950/50',
              }),
          ),
          h(
            'div',
            { class: 'fixed inset-0 w-screen overflow-y-auto pt-6 sm:pt-0' },
            h(
              'div',
              { class: 'grid min-h-full grid-rows-[1fr_auto] justify-items-center sm:grid-rows-[1fr_auto_3fr] sm:p-4' },
              h(
                TransitionChild,
                {
                  as: 'template',
                  enter: 'transition duration-100 ease-out',
                  enterFrom: 'opacity-0 translate-y-12 sm:translate-y-0 sm:scale-95',
                  enterTo: 'opacity-100 translate-y-0 sm:scale-100',
                  leave: 'transition duration-100 ease-in',
                  leaveFrom: 'opacity-100 translate-y-0 sm:scale-100',
                  leaveTo: 'opacity-0 translate-y-12 sm:translate-y-0 sm:scale-95',
                },
                () =>
                  h(
                    DialogPanel,
                    {
                      ...rest,
                      class: [
                        klass,
                        sizes[props.size],
                        'row-start-2 w-full min-w-0 rounded-t-3xl bg-white p-(--gutter) shadow-lg ring-1 ring-zinc-950/10 [--gutter:--spacing(8)] sm:mb-auto sm:rounded-2xl dark:bg-zinc-900 dark:ring-white/10 forced-colors:outline',
                        'transition duration-100 will-change-transform',
                      ],
                    },
                    slots,
                  ),
              ),
            ),
          ),
        ]),
      )
    }
  },
})

type Ctx = { slots: any; attrs: any }

export function DialogTitle(_: unknown, { slots, attrs }: Ctx) {
  return h(
    HDialogTitle,
    {
      ...attrs,
      class: [attrs.class, 'text-lg/6 font-semibold text-balance text-zinc-950 sm:text-base/6 dark:text-white'],
    },
    slots,
  )
}

export function DialogDescription(_: unknown, { slots, attrs }: Ctx) {
  return h(
    HDialogDescription,
    {
      as: 'p',
      'data-slot': 'text',
      ...attrs,
      class: [attrs.class, 'mt-2 text-pretty text-base/6 text-zinc-500 sm:text-sm/6 dark:text-zinc-400'],
    },
    slots,
  )
}

export function DialogBody(_: unknown, { slots, attrs }: Ctx) {
  return h('div', { ...attrs, class: [attrs.class, 'mt-6'] }, slots.default?.())
}

export function DialogActions(_: unknown, { slots, attrs }: Ctx) {
  return h(
    'div',
    {
      ...attrs,
      class: [
        attrs.class,
        'mt-8 flex flex-col-reverse items-center justify-end gap-3 *:w-full sm:flex-row sm:*:w-auto',
      ],
    },
    slots.default?.(),
  )
}
