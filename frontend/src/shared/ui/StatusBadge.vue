<script setup lang="ts">
import { computed } from 'vue'
import { statusLabel, statusTone } from '@/shared/lib/format'

const props = defineProps<{ status: string }>()
const tone = computed(() => statusTone(props.status))
</script>

<template>
  <span class="status-badge" :class="`is-${tone}`">{{ statusLabel(status) }}</span>
</template>
