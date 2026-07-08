<script setup lang="ts">
import { RouterView } from 'vue-router'
import { useSession } from '@/domains/auth/session'

useSession()
</script>

<template>
  <RouterView />
</template>
