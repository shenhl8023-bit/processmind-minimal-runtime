<template>
  <div class="page-header">
    <div>
      <h1>{{ title }}</h1>
      <p class="page-desc">{{ description }}</p>
    </div>
    <span v-if="badgeVisible" :class="badgeClass">
      {{ badgeText }}
    </span>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  title: string
  description: string
  badgeVisible?: boolean
  badgeClass?: string
  badgeText?: string
}>(), {
  badgeVisible: true,
  badgeClass: 'tag tag-success',
  badgeText: '',
})
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 19px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 4px;
  letter-spacing: -0.01em;
}

.page-desc {
  font-size: 14px;
  color: #64748b;
  line-height: 1.6;
}

.page-header .tag {
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 700;
  border-radius: 999px;
  white-space: nowrap;
}

.page-header .tag-success {
  background: #ecfdf5;
  color: #059669;
  border: 1px solid #a7f3d0;
  box-shadow: 0 2px 8px rgba(16, 185, 129, 0.06);
}

.page-header .tag-warning {
  background: #fff7ed;
  color: #c2410c;
  border: 1px solid #fdba74;
  box-shadow: 0 2px 8px rgba(234, 88, 12, 0.06);
}
</style>
