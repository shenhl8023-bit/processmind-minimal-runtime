<template>
  <div class="card project-card">
    <div class="project-card-header">
      <div class="project-card-title-row">
        <svg class="header-icon-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="7" height="9" rx="1" />
          <rect x="14" y="3" width="7" height="5" rx="1" />
          <rect x="14" y="12" width="7" height="9" rx="1" />
          <rect x="3" y="16" width="7" height="5" rx="1" />
        </svg>
        <span class="project-card-title">上传任务资料</span>
      </div>
      <p class="project-card-desc">先创建工艺规程规则任务，再按任务上传文件。每个任务的文档、规则和生成结果独立保存。</p>
    </div>
    <div class="project-board">
      <button class="project-tile project-tile-new" :disabled="creatingProject" @click="$emit('create')">
        <div class="new-tile-inner">
          <div class="new-tile-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          </div>
          <div class="new-tile-text">新建任务</div>
        </div>
      </button>

      <div
        v-for="project in projects"
        :key="project.id"
        :class="['project-tile', { active: selectedProjectId === String(project.id) }]"
        @click="$emit('select', project.id)"
      >
        <div class="project-tile-accent"></div>
        <div class="project-tile-body">
          <div class="project-tile-head">
            <div class="project-icon-badge">
              <svg v-if="project.status === 'GENERATED'" class="project-badge-svg status-gen" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              <svg v-else-if="project.status === 'ROUTE_SET_READY'" class="project-badge-svg status-ready" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M4.5 16.5c-1.5 1.26-2.5 3.19-2.5 5.5h20c0-2.31-1-4.24-2.5-5.5" />
                <path d="M12 2v12" />
                <path d="M12 14a3 3 0 1 0 0-6 3 3 0 0 0 0 6z" />
              </svg>
              <svg v-else class="project-badge-svg status-def" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <div class="project-head-info">
              <div class="project-name">{{ project.name }}</div>
              <div class="project-meta">
                <span class="project-mode-chip">工艺规程规则</span>
                <span v-if="profileShortLabel(project.profile)" class="project-profile-chip">{{ profileShortLabel(project.profile) }}</span>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
                {{ formatTime(project.updated_at || project.created_at) }}
              </div>
            </div>
          </div>
          <div class="project-tile-footer">
            <span :class="['project-status-pill', 'pill-' + (project.status || 'DRAFT').toLowerCase()]">
              <span class="status-dot"></span>
              {{ projectStatusText(project.status) }}
            </span>
            <div class="project-tile-actions">
              <span v-if="selectedProjectId === String(project.id)" class="current-badge">当前</span>
              <button class="tile-delete-btn" @click.stop="$emit('remove', project.id)" title="删除任务">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="project-hint">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align: -2px; margin-right: 4px;"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
      删除任务会一起删除该任务下的上传文件、提炼规则和生成结果
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  projects: any[]
  selectedProjectId: string
  creatingProject: boolean
  profileShortLabel: (profileKey?: string) => string
  formatTime: (value: string) => string
  projectStatusText: (status: string) => string
}>()

defineEmits<{
  create: []
  select: [projectId: number]
  remove: [projectId: number]
}>()
</script>

<style scoped>
.project-card {
  padding: 12px 14px;
  margin-bottom: 10px;
  flex-shrink: 0;
}

.project-card-header {
  border-bottom: 1px solid var(--border-light);
  padding-bottom: 8px;
  margin-bottom: 10px;
}

.project-card-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.project-card-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.project-card-desc {
  margin: 4px 0 0 22px;
  font-size: 11.5px;
  color: var(--text-muted);
  line-height: 1.45;
}
.project-board {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 4px;
  max-height: 140px;
  overflow-y: auto;
  padding: 8px;
  margin: -8px;
}
.project-board::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
.project-board::-webkit-scrollbar-track {
  background: transparent;
}
.project-board::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.4);
  border-radius: 999px;
}
.project-board::-webkit-scrollbar-thumb:hover {
  background: rgba(100, 116, 139, 0.55);
}
.project-tile-new {
  display: flex;
  align-items: stretch;
  border: 1.5px dashed #cbd5e1;
  border-radius: var(--radius-sm);
  background: transparent;
  cursor: pointer;
  transition: all 0.2s ease;
  min-height: 60px;
  height: 60px;
  overflow: hidden;
  margin: 2px;
}
.project-tile-new:hover {
  border-color: var(--accent);
  background: var(--accent-light);
  transform: translateY(-1px);
}
.new-tile-inner {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  width: 100%;
  gap: 8px;
  padding: 0 12px;
}
.new-tile-icon {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--accent), #6366f1);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}
.project-tile-new:hover .new-tile-icon {
  transform: scale(1.1) rotate(90deg);
}
.new-tile-text {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}
.project-tile-new:hover .new-tile-text {
  color: var(--accent);
}
.project-tile {
  display: flex;
  align-items: stretch;
  text-align: left;
  border: 1.5px solid var(--border-light);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  transition: all 0.2s ease;
  cursor: pointer;
  overflow: hidden;
  min-height: 60px;
  height: 60px;
  box-shadow: var(--shadow-sm);
  position: relative;
  margin: 2px;
}
.project-tile:hover {
  border-color: #cbd5e1;
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}
.project-tile.active {
  border: 1.5px solid var(--accent);
  box-shadow: 0 2px 8px rgba(79, 70, 229, 0.08);
}
.project-tile-accent {
  width: 3px;
  background: linear-gradient(180deg, #d0d5dd 0%, #e8eaed 100%);
  flex-shrink: 0;
  transition: background 0.2s ease;
}
.project-tile.active .project-tile-accent {
  background: linear-gradient(180deg, var(--accent) 0%, #818cf8 100%);
}
.project-tile-body {
  flex: 1;
  padding: 6px 10px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-width: 0;
}
.project-tile-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 0;
  min-width: 0;
}
.project-icon-badge {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: var(--bg-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.project-tile.active .project-icon-badge {
  background: var(--accent-light);
}
.project-head-info {
  flex: 1;
  min-width: 0;
}
.project-name {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.2;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.project-meta {
  display: none;
}
.project-tile-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 2px;
}
.project-status-pill {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px;
  border-radius: 20px;
  font-size: 10px;
  font-weight: 600;
}
.status-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
}
.pill-draft { background: #fef3c7; color: #92400e; }
.pill-draft .status-dot { background: #f59e0b; }
.pill-uploaded { background: #dbeafe; color: #1e40af; }
.pill-uploaded .status-dot { background: #3b82f6; }
.pill-extracted { background: #e0e7ff; color: #3730a3; }
.pill-extracted .status-dot { background: #6366f1; }
.pill-generated { background: #dcfce7; color: #166534; }
.pill-generated .status-dot { background: #22c55e; }
.pill-route_set_ready { background: #ede9fe; color: #5b21b6; }
.pill-route_set_ready .status-dot { background: #8b5cf6; }
.pill-extracting { background: #cffafe; color: #155e75; }
.pill-extracting .status-dot { background: #06b6d4; }
.pill-extract_error { background: #fee2e2; color: #991b1b; }
.pill-extract_error .status-dot { background: #ef4444; }
.project-tile-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.current-badge {
  font-size: 9px;
  font-weight: 700;
  color: var(--accent);
  background: var(--accent-light);
  padding: 1px 5px;
  border-radius: 20px;
}
.tile-delete-btn {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  border: none;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  transition: all 0.2s ease;
  opacity: 0;
}
.project-tile:hover .tile-delete-btn {
  opacity: 1;
}
.tile-delete-btn:hover {
  background: #fee2e2;
  color: #b91c1c;
}
.project-hint {
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
}
</style>
