<script setup lang="ts">
import { Check, ChevronDown } from '@lucide/vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { SelectOption, SelectValue } from './select'

const props = withDefaults(
  defineProps<{
    id: string
    label: string
    options: readonly SelectOption[]
    name?: string
    placeholder?: string
    disabled?: boolean
    required?: boolean
    describedBy?: string
  }>(),
  {
    name: undefined,
    placeholder: 'Выберите значение',
    disabled: false,
    required: false,
    describedBy: undefined,
  },
)

const emit = defineEmits<{
  change: [value: SelectValue]
}>()

const model = defineModel<SelectValue>({ required: true })
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const open = ref(false)
const activeIndex = ref(-1)
const isMobile = ref(false)
const typeahead = ref('')
let mediaQuery: MediaQueryList | undefined
let typeaheadTimer: number | undefined

const triggerId = computed(() => `${props.id}-trigger`)
const labelId = computed(() => `${props.id}-label`)
const valueId = computed(() => `${props.id}-value`)
const listboxId = computed(() => `${props.id}-listbox`)
const selectedIndex = computed(() =>
  props.options.findIndex((option) => Object.is(option.value, model.value)),
)
const selectedOption = computed(() => props.options[selectedIndex.value])
const activeDescendant = computed(() =>
  open.value && activeIndex.value >= 0
    ? `${listboxId.value}-option-${activeIndex.value}`
    : undefined,
)

function firstEnabledIndex() {
  return props.options.findIndex((option) => !option.disabled)
}

function lastEnabledIndex() {
  for (let index = props.options.length - 1; index >= 0; index -= 1) {
    if (!props.options[index]?.disabled) return index
  }
  return -1
}

function moveActive(direction: 1 | -1) {
  if (props.options.length === 0) return
  let index = activeIndex.value

  for (let attempts = 0; attempts < props.options.length; attempts += 1) {
    index = (index + direction + props.options.length) % props.options.length
    if (!props.options[index]?.disabled) {
      activeIndex.value = index
      return
    }
  }
}

function openMenu() {
  if (props.disabled || open.value) return
  open.value = true
  activeIndex.value = selectedIndex.value >= 0 ? selectedIndex.value : firstEnabledIndex()
}

function closeMenu({ restoreFocus = false } = {}) {
  if (!open.value) return
  open.value = false
  activeIndex.value = -1
  if (restoreFocus) void nextTick(() => trigger.value?.focus())
}

function toggleMenu() {
  if (open.value) closeMenu()
  else openMenu()
}

function selectOption(option: SelectOption) {
  if (props.disabled || option.disabled) return
  model.value = option.value
  emit('change', option.value)
  closeMenu({ restoreFocus: true })
}

function selectActive() {
  const option = props.options[activeIndex.value]
  if (option) selectOption(option)
}

function handleKeydown(event: KeyboardEvent) {
  if (props.disabled) return

  switch (event.key) {
    case 'ArrowDown':
      event.preventDefault()
      if (!open.value) openMenu()
      else moveActive(1)
      break
    case 'ArrowUp':
      event.preventDefault()
      if (!open.value) openMenu()
      else moveActive(-1)
      break
    case 'Home':
      event.preventDefault()
      openMenu()
      activeIndex.value = firstEnabledIndex()
      break
    case 'End':
      event.preventDefault()
      openMenu()
      activeIndex.value = lastEnabledIndex()
      break
    case 'Enter':
    case ' ':
      event.preventDefault()
      if (open.value) selectActive()
      else openMenu()
      break
    case 'Escape':
      if (open.value) {
        event.preventDefault()
        closeMenu()
      }
      break
    case 'Tab':
      closeMenu()
      break
    default:
      if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
        findByTypeahead(event.key)
      }
  }
}

function findByTypeahead(character: string) {
  window.clearTimeout(typeaheadTimer)
  typeahead.value += character.toLocaleLowerCase()
  typeaheadTimer = window.setTimeout(() => {
    typeahead.value = ''
  }, 700)

  const matchIndex = props.options.findIndex(
    (option) => !option.disabled && option.label.toLocaleLowerCase().startsWith(typeahead.value),
  )
  if (matchIndex < 0) return
  openMenu()
  activeIndex.value = matchIndex
}

function handleNativeChange(event: Event) {
  const target = event.target as HTMLSelectElement
  const option = props.options.find((item) => String(item.value) === target.value)
  if (!option) return
  model.value = option.value
  emit('change', option.value)
}

function handleInvalid(event: Event) {
  if (isMobile.value) return
  event.preventDefault()
  trigger.value?.focus()
}

function handleDocumentPointerDown(event: PointerEvent) {
  if (root.value && !root.value.contains(event.target as Node)) closeMenu()
}

function handleMediaChange(event: MediaQueryListEvent | MediaQueryList) {
  isMobile.value = event.matches
  if (event.matches) closeMenu()
}

watch(
  () => props.disabled,
  (disabled) => {
    if (disabled) closeMenu()
  },
)

onMounted(() => {
  mediaQuery = window.matchMedia('(max-width: 760px)')
  handleMediaChange(mediaQuery)
  mediaQuery.addEventListener('change', handleMediaChange)
  document.addEventListener('pointerdown', handleDocumentPointerDown)
})

onBeforeUnmount(() => {
  window.clearTimeout(typeaheadTimer)
  mediaQuery?.removeEventListener('change', handleMediaChange)
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
})
</script>

<template>
  <div ref="root" class="field select-field" :class="{ 'is-open': open, 'is-disabled': disabled }">
    <label :id="labelId" :for="isMobile ? id : triggerId">{{ label }}</label>
    <div class="select-field__control">
      <select
        :id="id"
        class="select-field__native"
        :class="{ 'is-form-proxy': !isMobile }"
        :name="name"
        :value="String(model)"
        :disabled="disabled"
        :required="required"
        :aria-describedby="describedBy"
        :aria-hidden="!isMobile || undefined"
        :tabindex="isMobile ? 0 : -1"
        @change="handleNativeChange"
        @invalid="handleInvalid"
      >
        <option v-if="selectedIndex < 0" value="" disabled>{{ placeholder }}</option>
        <option
          v-for="option in options"
          :key="`${typeof option.value}:${option.value}`"
          :value="String(option.value)"
          :disabled="option.disabled"
        >
          {{ option.label }}
        </option>
      </select>

      <template v-if="!isMobile">
        <button
          :id="triggerId"
          ref="trigger"
          class="select-field__trigger"
          type="button"
          role="combobox"
          aria-haspopup="listbox"
          :aria-expanded="open"
          :aria-controls="listboxId"
          :aria-activedescendant="activeDescendant"
          :aria-labelledby="`${labelId} ${valueId}`"
          :aria-describedby="describedBy"
          :aria-required="required || undefined"
          :disabled="disabled"
          @click="toggleMenu"
          @keydown="handleKeydown"
        >
          <span :id="valueId" class="select-field__value" :class="{ 'is-placeholder': !selectedOption }">
            {{ selectedOption?.label ?? placeholder }}
          </span>
          <ChevronDown class="select-field__chevron" :size="17" aria-hidden="true" />
        </button>

        <ul v-if="open" :id="listboxId" class="select-field__menu" role="listbox" :aria-labelledby="labelId">
          <li
            v-for="(option, index) in options"
            :id="`${listboxId}-option-${index}`"
            :key="`${typeof option.value}:${option.value}`"
            class="select-field__option"
            :class="{ 'is-active': activeIndex === index, 'is-selected': Object.is(option.value, model) }"
            role="option"
            :aria-selected="Object.is(option.value, model)"
            :aria-disabled="option.disabled || undefined"
            @pointerenter="!option.disabled && (activeIndex = index)"
            @mousedown.prevent
            @click="selectOption(option)"
          >
            <span>{{ option.label }}</span>
            <Check v-if="Object.is(option.value, model)" :size="16" aria-hidden="true" />
          </li>
        </ul>
      </template>
    </div>
  </div>
</template>
