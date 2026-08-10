<script setup lang="ts">
// Search / sort / page-size bar shared by the certificate and host lists. Paging buttons
// live in ListPagination, which sits below the table like Catalyst's pagination does.
import { Button, Select, Input, Text } from './catalyst'

const props = defineProps<{
  search: string
  sort: string
  order: 'asc' | 'desc'
  limit: number
  offset: number
  total: number
  sorts: { value: string; label: string }[]
  placeholder?: string
}>()

const emit = defineEmits<{
  (e: 'update:search', value: string): void
  (e: 'update:sort', value: string): void
  (e: 'update:order', value: 'asc' | 'desc'): void
  (e: 'update:limit', value: number): void
  (e: 'update:offset', value: number): void
}>()
</script>

<template>
  <div class="flex flex-wrap items-center gap-3">
    <Input
      :model-value="search"
      :placeholder="placeholder || 'Search…'"
      type="search"
      data-testid="list-search"
      class="max-w-56"
      @update:model-value="emit('update:search', $event); emit('update:offset', 0)"
    />
    <div class="w-48">
      <Select
        :model-value="sort"
        data-testid="list-sort"
        @update:model-value="emit('update:sort', $event)"
      >
        <option v-for="option in sorts" :key="option.value" :value="option.value">
          {{ option.label }}
        </option>
      </Select>
    </div>
    <Button
      outline
      data-testid="list-order"
      :title="order === 'asc' ? 'Ascending' : 'Descending'"
      @click="emit('update:order', order === 'asc' ? 'desc' : 'asc')"
    >
      {{ order === 'asc' ? '↑' : '↓' }}
    </Button>

    <div class="ml-auto flex items-center gap-3">
      <div class="w-22">
        <Select
          :model-value="limit"
          data-testid="list-limit"
          @update:model-value="emit('update:limit', Number($event)); emit('update:offset', 0)"
        >
          <option :value="10">10</option>
          <option :value="25">25</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
        </Select>
      </div>
      <Text data-testid="list-range" class="whitespace-nowrap">
        {{ total === 0 ? '0' : `${offset + 1}–${Math.min(offset + limit, total)}` }} of {{ total }}
      </Text>
    </div>
  </div>
</template>
