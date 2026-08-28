<script setup lang="ts">
// Catalyst pagination (Previous / page numbers / Next) for the offset-paged lists.
import { computed } from 'vue'
import { Pagination, PaginationGap, PaginationList, PaginationNext, PaginationPage, PaginationPrevious } from './catalyst'

const props = defineProps<{
  offset: number
  limit: number
  total: number
}>()

const emit = defineEmits<{ (e: 'update:offset', value: number): void }>()

const pageCount = computed(() => Math.max(1, Math.ceil(props.total / props.limit)))
const current = computed(() => Math.floor(props.offset / props.limit) + 1)

// Windowed page list: 1 … n-1 n n+1 … last, with nulls marking the gaps.
const pages = computed<(number | null)[]>(() => {
  const last = pageCount.value
  const near = new Set([1, last, current.value - 1, current.value, current.value + 1])
  const list: (number | null)[] = []
  for (let page = 1; page <= last; page += 1) {
    if (near.has(page)) list.push(page)
    else if (list[list.length - 1] !== null) list.push(null)
  }
  return list
})

function goTo(page: number) {
  emit('update:offset', (page - 1) * props.limit)
}
</script>

<template>
  <Pagination>
    <PaginationPrevious data-testid="list-prev" :disabled="current <= 1" @click="goTo(current - 1)" />
    <PaginationList>
      <template v-for="(page, index) in pages">
        <PaginationGap v-if="page === null" :key="`gap-${index}`" />
        <PaginationPage v-else :key="page" :current="page === current" @click="goTo(page)">
          {{ page }}
        </PaginationPage>
      </template>
    </PaginationList>
    <PaginationNext data-testid="list-next" :disabled="current >= pageCount" @click="goTo(current + 1)" />
  </Pagination>
</template>
