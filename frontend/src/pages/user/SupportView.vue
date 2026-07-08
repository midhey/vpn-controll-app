<script setup lang="ts">
import { Copy, RotateCw } from '@lucide/vue'
import { onMounted, ref } from 'vue'
import * as supportApi from '@/domains/support/api'
import { errorMessage } from '@/shared/api/client'
import type { SupportHistoryOut, SupportViewOut } from '@/shared/api/types'
import { copyText } from '@/shared/lib/copy'
import { formatDate, formatMoney } from '@/shared/lib/format'
import EmptyState from '@/shared/ui/EmptyState.vue'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'
import LoadingState from '@/shared/ui/LoadingState.vue'

const view = ref<SupportViewOut | null>(null)
const history = ref<SupportHistoryOut | null>(null)
const loading = ref(true)
const error = ref('')
const copied = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [supportView, supportHistory] = await Promise.all([
      supportApi.getSupportView(),
      supportApi.getSupportHistory(),
    ])
    view.value = supportView
    history.value = supportHistory
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    loading.value = false
  }
}

async function copy(value: string, key: string) {
  await copyText(value)
  copied.value = key
  window.setTimeout(() => {
    copied.value = ''
  }, 1400)
}

onMounted(load)
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <h1>Поддержка</h1>
        <p>Реквизиты и история взносов отображаются только если backend разрешил их текущему пользователю.</p>
      </div>
      <div class="page-actions">
        <button class="ghost-button" type="button" @click="load"><RotateCw :size="16" /> Обновить</button>
      </div>
    </header>

    <LoadingState v-if="loading" />
    <ErrorBanner v-else-if="error" :message="error" />

    <template v-else-if="view && history">
      <EmptyState v-if="!view.visible" title="Поддержка скрыта" text="Для вашего доступа реквизиты и история не показываются." />

      <template v-else>
        <section class="panel">
          <div class="panel-header">
            <div>
              <h2>{{ view.title || 'Поддержка сервера' }}</h2>
              <p>{{ view.description || 'Реквизиты администратора VPN.' }}</p>
            </div>
          </div>
          <div class="panel-body support-grid">
            <div v-if="view.sbp_phone" class="support-item">
              <span>СБП</span>
              <strong>{{ view.sbp_phone }}</strong>
              <button class="ghost-button" type="button" @click="copy(view.sbp_phone, 'phone')">
                <Copy :size="16" /> {{ copied === 'phone' ? 'Скопировано' : 'Копировать' }}
              </button>
            </div>
            <div v-if="view.bank_name" class="support-item">
              <span>Банк</span>
              <strong>{{ view.bank_name }}</strong>
            </div>
            <div v-if="view.extra_contact" class="support-item">
              <span>Контакт</span>
              <strong>{{ view.extra_contact }}</strong>
              <button class="ghost-button" type="button" @click="copy(view.extra_contact, 'contact')">
                <Copy :size="16" /> {{ copied === 'contact' ? 'Скопировано' : 'Копировать' }}
              </button>
            </div>
            <div class="support-item">
              <span>Месяц</span>
              <strong>{{ formatMoney(view.monthly_cost_amount) }}</strong>
            </div>
            <div class="support-item">
              <span>Резерв</span>
              <strong>{{ formatMoney(view.reserve_amount) }}</strong>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="panel-header">
            <div>
              <h2>История взносов</h2>
              <p>Данные записывает администратор.</p>
            </div>
          </div>
          <EmptyState v-if="history.items.length === 0" title="История пуста" />
          <div v-else class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Дата</th>
                  <th>Сумма</th>
                  <th>Период</th>
                  <th>Комментарий</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in history.items" :key="item.id">
                  <td>{{ formatDate(item.recorded_at) }}</td>
                  <td>{{ formatMoney(item.amount, item.currency) }}</td>
                  <td>{{ item.period_label || '—' }}</td>
                  <td>{{ item.comment || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </template>
  </section>
</template>

<style scoped lang="scss">
.support-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.support-item {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: rgba(10, 16, 32, 0.52);

  span {
    color: var(--muted);
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
  }

  strong {
    overflow-wrap: anywhere;
    color: var(--text-strong);
  }
}

@media (max-width: 760px) {
  .support-grid {
    grid-template-columns: 1fr;
  }
}
</style>
