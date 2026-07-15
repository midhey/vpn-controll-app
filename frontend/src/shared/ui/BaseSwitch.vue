<script setup lang="ts">
import { computed, useId } from 'vue'

const props = withDefaults(
  defineProps<{
    id?: string
    name?: string
    disabled?: boolean
  }>(),
  {
    id: undefined,
    name: undefined,
    disabled: false,
  },
)

const model = defineModel<boolean>({ required: true })
const generatedId = useId()
const inputId = computed(() => props.id || generatedId)
</script>

<template>
  <label class="switch" :class="{ 'is-disabled': disabled }" :for="inputId">
    <input
      :id="inputId"
      v-model="model"
      class="switch__input"
      type="checkbox"
      role="switch"
      :name="name"
      :disabled="disabled"
    />
    <span class="switch__control" aria-hidden="true">
      <span class="switch__thumb" />
    </span>
    <span class="switch__label"><slot /></span>
  </label>
</template>

<style scoped lang="scss">
.switch {
  position: relative;
  display: inline-flex;
  align-items: flex-start;
  gap: 9px;
  width: fit-content;
  color: var(--color-text);
  font-size: 13px;
  font-weight: 650;
  line-height: 22px;
  cursor: pointer;
}

.switch__input {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: 0;
  opacity: 0;
}

.switch__control {
  display: flex;
  flex: 0 0 38px;
  align-items: center;
  width: 38px;
  height: 22px;
  padding: 2px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-round);
  background: var(--color-field-background);
  transition:
    border-color var(--duration-fast),
    background-color var(--duration-fast),
    box-shadow var(--duration-fast);
}

.switch__thumb {
  width: 16px;
  height: 16px;
  border-radius: var(--radius-round);
  background: var(--color-text-muted);
  box-shadow: var(--shadow-surface);
  transform: translateX(0);
  transition:
    background-color var(--duration-fast),
    transform var(--duration-fast);
}

.switch:not(.is-disabled):hover .switch__control {
  border-color: var(--color-border-strong);
  background: var(--color-surface-elevated);
}

.switch__input:checked + .switch__control {
  border-color: var(--color-action-border);
  background: var(--color-action);
}

.switch__input:checked + .switch__control .switch__thumb {
  background: var(--color-action-text);
  transform: translateX(16px);
}

.switch:not(.is-disabled):hover .switch__input:checked + .switch__control {
  border-color: var(--color-action-focus-border);
  background: var(--color-action-hover);
}

.switch__input:focus-visible + .switch__control {
  border-color: var(--color-action-focus-border);
  box-shadow: 0 0 0 3px var(--color-action-focus-shadow);
}

.switch.is-disabled {
  color: var(--color-text-muted);
  cursor: not-allowed;
}

.switch__input:disabled + .switch__control {
  border-color: var(--color-border);
  background: var(--color-surface-muted);
  opacity: 0.62;
}

@media (prefers-reduced-motion: reduce) {
  .switch__control,
  .switch__thumb {
    transition: none;
  }
}
</style>
