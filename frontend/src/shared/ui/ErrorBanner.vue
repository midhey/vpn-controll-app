<script setup lang="ts">
defineProps<{ message: string }>()
</script>

<template>
  <div class="alert alert-danger" role="alert">
    {{ message }}
  </div>
</template>
