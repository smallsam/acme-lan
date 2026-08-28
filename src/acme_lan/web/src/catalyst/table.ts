// Vue port of Catalyst's table.tsx. The React context becomes provide/inject; the
// row-link (href) variant is unused in this app and omitted.
import { defineComponent, h, inject, provide, type InjectionKey } from 'vue'

type TableConfig = { bleed: boolean; dense: boolean; grid: boolean; striped: boolean }

const TableContext: InjectionKey<TableConfig> = Symbol('TableContext')
const defaults: TableConfig = { bleed: false, dense: false, grid: false, striped: false }

export const Table = defineComponent({
  name: 'CatalystTable',
  inheritAttrs: false,
  props: {
    bleed: { type: Boolean, default: false },
    dense: { type: Boolean, default: false },
    grid: { type: Boolean, default: false },
    striped: { type: Boolean, default: false },
  },
  setup(props, { slots, attrs }) {
    provide(TableContext, props)
    return () => {
      const { class: klass, ...rest } = attrs
      return h(
        'div',
        { class: 'flow-root' },
        h(
          'div',
          { ...rest, class: [klass, '-mx-(--gutter) overflow-x-auto whitespace-nowrap'] },
          h(
            'div',
            { class: ['inline-block min-w-full align-middle', !props.bleed && 'sm:px-(--gutter)'] },
            h('table', { class: 'min-w-full text-left text-sm/6 text-zinc-950 dark:text-white' }, slots.default?.()),
          ),
        ),
      )
    }
  },
})

export function TableHead(_: unknown, { slots, attrs }: { slots: any; attrs: any }) {
  return h('thead', { ...attrs, class: [attrs.class, 'text-zinc-500 dark:text-zinc-400'] }, slots.default?.())
}

export function TableBody(_: unknown, { slots, attrs }: { slots: any; attrs: any }) {
  return h('tbody', attrs, slots.default?.())
}

export const TableRow = defineComponent({
  name: 'CatalystTableRow',
  setup(_, { slots, attrs }) {
    const { striped } = inject(TableContext, defaults)
    return () =>
      h('tr', { ...attrs, class: [attrs.class, striped && 'even:bg-zinc-950/2.5 dark:even:bg-white/2.5'] }, slots.default?.())
  },
})

export const TableHeader = defineComponent({
  name: 'CatalystTableHeader',
  setup(_, { slots, attrs }) {
    const config = inject(TableContext, defaults)
    return () =>
      h(
        'th',
        {
          ...attrs,
          class: [
            attrs.class,
            'border-b border-b-zinc-950/10 px-4 py-2 font-medium first:pl-(--gutter,--spacing(2)) last:pr-(--gutter,--spacing(2)) dark:border-b-white/10',
            config.grid && 'border-l border-l-zinc-950/5 first:border-l-0 dark:border-l-white/5',
            !config.bleed && 'sm:first:pl-1 sm:last:pr-1',
          ],
        },
        slots.default?.(),
      )
  },
})

export const TableCell = defineComponent({
  name: 'CatalystTableCell',
  setup(_, { slots, attrs }) {
    const config = inject(TableContext, defaults)
    return () =>
      h(
        'td',
        {
          ...attrs,
          class: [
            attrs.class,
            'relative px-4 first:pl-(--gutter,--spacing(2)) last:pr-(--gutter,--spacing(2))',
            !config.striped && 'border-b border-zinc-950/5 dark:border-white/5',
            config.grid && 'border-l border-l-zinc-950/5 first:border-l-0 dark:border-l-white/5',
            config.dense ? 'py-2.5' : 'py-4',
            !config.bleed && 'sm:first:pl-1 sm:last:pr-1',
          ],
        },
        slots.default?.(),
      )
  },
})
