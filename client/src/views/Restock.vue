<template>
  <div class="restock">
    <div class="page-header">
      <h2>{{ t('restock.title') }}</h2>
      <p>{{ t('restock.description') }}</p>
    </div>

    <div class="card controls-card">
      <div class="controls">
        <div class="control">
          <label for="restock-budget">{{ t('restock.controls.budget') }}</label>
          <div class="budget-input">
            <span class="symbol">{{ symbol }}</span>
            <input
              id="restock-budget"
              v-model.number="budgetInput"
              type="number"
              min="0"
              step="any"
              @input="onBudgetInput"
              @keyup.enter="calculate"
            />
          </div>
          <div v-if="budgetError" class="field-error">{{ t('restock.budgetInvalid') }}</div>
        </div>
        <div class="control">
          <label for="restock-coverage">{{ t('restock.controls.coverage') }}</label>
          <select id="restock-coverage" v-model.number="coverageDays">
            <option v-for="d in coverageOptions" :key="d" :value="d">
              {{ t('restock.controls.days', { count: d }) }}
            </option>
          </select>
        </div>
        <div class="control">
          <label for="restock-lookback">{{ t('restock.controls.lookback') }}</label>
          <select id="restock-lookback" v-model.number="lookbackMonths">
            <option v-for="m in lookbackOptions" :key="m" :value="m">
              {{ t('restock.controls.months', { count: m }) }}
            </option>
          </select>
        </div>
        <button class="calc-btn" :disabled="loading" @click="calculate">
          {{ t('restock.controls.calculate') }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="loadFailed" class="error">{{ t('restock.loadError') }}</div>
    <div v-else-if="plan">
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">{{ t('restock.stats.budget') }}</div>
          <div class="stat-value">{{ formatCurrency(lastBudgetUsd ?? plan.budget) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restock.stats.allocated') }}</div>
          <div class="stat-value">{{ formatCurrency(plan.total_allocated) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restock.stats.remaining') }}</div>
          <div class="stat-value">{{ formatCurrency(plan.remaining_budget) }}</div>
        </div>
        <div class="stat-card info">
          <div class="stat-label">{{ t('restock.stats.totalNeed') }}</div>
          <div class="stat-value">{{ formatCurrency(plan.total_need_cost) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restock.stats.funded') }}</div>
          <div class="stat-value">{{ plan.items_funded }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restock.stats.partial') }}</div>
          <div class="stat-value">{{ plan.items_partial }}</div>
        </div>
        <div class="stat-card" :class="{ warning: plan.items_unfunded > 0 }">
          <div class="stat-label">{{ t('restock.stats.unfunded') }}</div>
          <div class="stat-value">{{ plan.items_unfunded }}</div>
        </div>
      </div>

      <div class="card">
        <div class="bar-label">
          {{ t('restock.bar.label', { percent: allocatedPercent.toFixed(1) }) }}
        </div>
        <div class="alloc-bar" role="img" :aria-label="t('restock.bar.label', { percent: allocatedPercent.toFixed(1) })">
          <div class="alloc-fill" :style="{ width: allocatedPercent + '%' }"></div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restock.table.title') }} ({{ recommendations.length }})</h3>
        </div>
        <div v-if="recommendations.length === 0" class="empty">{{ t('restock.empty') }}</div>
        <div v-else class="table-container">
          <table class="restock-table">
            <thead>
              <tr>
                <th>{{ t('restock.table.rank') }}</th>
                <th>{{ t('restock.table.sku') }}</th>
                <th>{{ t('restock.table.name') }}</th>
                <th>{{ t('restock.table.warehouse') }}</th>
                <th class="num">{{ t('restock.table.onHand') }}</th>
                <th class="num">{{ t('restock.table.reorderPoint') }}</th>
                <th class="num">{{ t('restock.table.avgDemand') }}</th>
                <th class="num">{{ t('restock.table.daysOfCover') }}</th>
                <th class="num">{{ t('restock.table.recommendedQty') }}</th>
                <th class="num">{{ t('restock.table.unitCost') }}</th>
                <th class="num">{{ t('restock.table.lineCost') }}</th>
                <th>{{ t('restock.table.status') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="r in recommendations"
                :key="r.sku"
                :class="{ 'below-reorder': r.below_reorder_point }"
              >
                <td>{{ r.rank }}</td>
                <td><strong>{{ r.sku }}</strong></td>
                <td>{{ r.name }}</td>
                <td>{{ translateWarehouse(r.warehouse) }}</td>
                <td class="num">{{ r.quantity_on_hand }}</td>
                <td class="num">
                  {{ r.reorder_point }}
                  <span v-if="r.below_reorder_point" class="below-tag">{{ t('restock.table.belowReorder') }}</span>
                </td>
                <td class="num">{{ r.avg_monthly_demand.toFixed(1) }}</td>
                <td class="num">
                  <span v-if="r.days_of_cover == null" class="muted">{{ t('restock.table.noDemand') }}</span>
                  <span v-else>{{ r.days_of_cover.toFixed(1) }}</span>
                </td>
                <td class="num">{{ r.recommended_qty }} / {{ r.need_qty }}</td>
                <td class="num">{{ formatCurrency(r.unit_cost) }}</td>
                <td class="num">{{ formatCurrency(r.line_cost) }}</td>
                <td>
                  <span class="badge" :class="statusClass(r.status)">{{ t('restock.status.' + r.status) }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <div v-else class="card prompt">{{ t('restock.prompt') }}</div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'
import { formatCurrency as formatCurrencyUtil, convertAmount, convertToUSD, currencySymbol } from '../utils/currency'

const { selectedLocation, selectedCategory } = useFilters()
const { t, currentCurrency, translateWarehouse } = useI18n()

const DEFAULT_BUDGET_USD = 50000
const coverageOptions = [14, 30, 60, 90]
const lookbackOptions = [1, 3, 6, 12]

// Internal USD budget is the source of truth; budgetInput is the displayed value
const budgetUsd = ref(DEFAULT_BUDGET_USD)
const lastBudgetUsd = ref(null)
const displayBudget = cur => {
  const v = convertAmount(budgetUsd.value, cur)
  return cur === 'JPY' ? v : Math.round(v * 100) / 100
}
const budgetInput = ref(displayBudget(currentCurrency.value))
const coverageDays = ref(30)
const lookbackMonths = ref(3)

const plan = ref(null)
const loading = ref(false)
const loadFailed = ref(false)
const budgetError = ref(false)
let reqId = 0

const formatCurrency = v => formatCurrencyUtil(v, currentCurrency.value)
const symbol = computed(() => currencySymbol(currentCurrency.value))

const recommendations = computed(() => plan.value?.recommendations ?? [])
const allocatedPercent = computed(() => {
  if (!plan.value || !(plan.value.budget > 0)) return 0
  return Math.min(100, Math.max(0, (plan.value.total_allocated / plan.value.budget) * 100))
})

const statusClass = status => ({
  funded: 'success',
  partial: 'warning',
  unfunded: 'danger'
}[status] || 'info')

const onBudgetInput = () => {
  const b = Number(budgetInput.value)
  budgetUsd.value = budgetInput.value === '' || !Number.isFinite(b)
    ? NaN
    : convertToUSD(b, currentCurrency.value)
}

const fetchPlan = async usd => {
  const id = ++reqId
  loading.value = true
  loadFailed.value = false
  try {
    const result = await api.getRestockRecommendations({
      budget: usd,
      coverageDays: coverageDays.value,
      lookbackMonths: lookbackMonths.value,
      warehouse: selectedLocation.value,
      category: selectedCategory.value
    })
    if (id !== reqId) return
    plan.value = result
    lastBudgetUsd.value = usd
  } catch (err) {
    if (id !== reqId) return
    plan.value = null
    loadFailed.value = true
    console.error('Restock load error:', err)
  } finally {
    if (id === reqId) loading.value = false
  }
}

const calculate = () => {
  if (!Number.isFinite(budgetUsd.value) || budgetUsd.value <= 0) {
    budgetError.value = true
    return
  }
  budgetError.value = false
  fetchPlan(budgetUsd.value)
}

// Refetch on global filter change using the last submitted budget
watch([selectedLocation, selectedCategory], () => {
  if (plan.value && lastBudgetUsd.value != null) fetchPlan(lastBudgetUsd.value)
})

// Re-derive the displayed input from the USD source of truth on currency change
watch(currentCurrency, cur => {
  if (Number.isFinite(budgetUsd.value) && budgetUsd.value > 0) {
    budgetInput.value = displayBudget(cur)
  }
})
</script>

<style scoped>
.controls-card { padding: 1rem 1.25rem; }
.controls { display: flex; flex-wrap: wrap; gap: 1rem; align-items: flex-end; }
.control { display: flex; flex-direction: column; gap: 0.25rem; }
.control label { font-size: 0.75rem; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.04em; }
.control select, .budget-input input {
  padding: 0.5rem 0.75rem; border: 1px solid #e2e8f0; border-radius: 6px;
  font-size: 0.875rem; color: #0f172a; background: #fff;
}
.budget-input { display: flex; align-items: center; gap: 0.5rem; }
.budget-input .symbol { color: #64748b; font-weight: 600; }
.budget-input input { width: 10rem; }
.field-error { color: #991b1b; font-size: 0.8rem; }
.calc-btn {
  padding: 0.5rem 1.25rem; background: #0f172a; color: #fff; border: none;
  border-radius: 6px; font-size: 0.875rem; cursor: pointer;
}
.calc-btn:hover:not(:disabled) { background: #334155; }
.calc-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.prompt, .empty { padding: 1.5rem; color: #64748b; text-align: center; }
.bar-label { padding: 0.75rem 1.25rem 0.5rem; font-size: 0.8rem; color: #64748b; }
.alloc-bar { height: 10px; background: #e2e8f0; border-radius: 5px; margin: 0 1.25rem 1rem; overflow: hidden; }
.alloc-fill { height: 100%; background: #475569; border-radius: 5px; }
.restock-table .num { text-align: right; white-space: nowrap; }
.muted { color: #94a3b8; }
.below-reorder td { background: #fecaca; }
.below-reorder td:first-child { box-shadow: inset 3px 0 0 #dc2626; }
.below-tag { margin-left: 0.4rem; font-size: 0.7rem; color: #991b1b; font-weight: 600; }
</style>
