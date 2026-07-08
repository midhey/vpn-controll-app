<script setup lang="ts">
import { Check, Copy } from '@lucide/vue'
import { ref } from 'vue'
import { copyText } from '@/shared/lib/copy'

const props = defineProps<{
  label: string
  value: string
  multiline?: boolean
}>()

const copied = ref(false)

async function copy() {
  await copyText(props.value)
  copied.value = true
  window.setTimeout(() => {
    copied.value = false
  }, 1600)
}
</script>

<template>
  <div class="copy-field">
    <div class="copy-field-header">
      <span>{{ label }}</span>
      <button class="ghost-button" type="button" @click="copy">
        <Check v-if="copied" :size="16" />
        <Copy v-else :size="16" />
        {{ copied ? 'Скопировано' : 'Копировать' }}
      </button>
    </div>
    <pre v-if="multiline">{{ value }}</pre>
    <code v-else>{{ value }}</code>
  </div>
</template>
