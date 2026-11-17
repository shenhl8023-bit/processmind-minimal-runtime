<template>
  <div class="settings-view">
    <div class="page-header">
      <h1>系统模型配置</h1>
      <p class="page-desc">配置大模型参数，支持 NVIDIA NIM、DeepSeek、硅基流动等 OpenAI 兼容接口。</p>
    </div>

    <div class="settings-container">
      <div class="card settings-card">
        <div class="card-title">
          <span>⚙️</span> LLM 配置
        </div>
        
        <div class="settings-form">
          <div class="form-item">
            <label class="form-label">API 基础路径 (Base URL)</label>
            <div class="input-wrapper">
              <input 
                v-model="form.LLM_API_URL" 
                type="text" 
                placeholder="https://integrate.api.nvidia.com/v1/chat/completions" 
                class="form-input"
              />
            </div>
            <p class="form-hint">如果不包含 v1/chat/completions，系统会自动根据服务商补充。</p>
          </div>

          <div class="form-item">
            <label class="form-label">API Key</label>
            <div class="input-wrapper">
              <input 
                v-model="form.LLM_API_KEY" 
                :type="showKey ? 'text' : 'password'" 
                :placeholder="hasStoredKey ? '已保存，留空表示保持原值' : 'nvapi-...'" 
                class="form-input"
              />
              <button class="btn-toggle-eye" @click="showKey = !showKey">
                {{ showKey ? '👁️' : '🔒' }}
              </button>
            </div>
            <p v-if="hasStoredKey" class="form-hint">当前已保存密钥。输入新值会覆盖；留空保存则保持不变。</p>
            <button v-if="hasStoredKey" class="btn-text" @click="clearApiKey" :disabled="saving || testing || loadingSettings || !settingsLoaded">
              清空已保存的 API Key
            </button>
          </div>

          <div class="form-item">
            <label class="form-label">默认模型 (Model ID)</label>
            <div class="input-wrapper">
              <input 
                v-model="form.LLM_MODEL" 
                type="text" 
                placeholder="meta/llama-3.1-70b-instruct" 
                class="form-input"
              />
            </div>
          </div>

          <div class="form-footer">
            <div v-if="saveStatus" :class="['status-msg', saveStatus.type]">
              {{ saveStatus.msg }}
            </div>
            <button class="btn btn-outline" @click="testConnection" :disabled="testing || saving || loadingSettings || !settingsLoaded">
              {{ testing ? '测试中...' : '⚡️ 测试连接' }}
            </button>
            <button class="btn btn-primary" @click="saveSettings" :disabled="saving || testing || loadingSettings || !settingsLoaded">
              {{ saving ? '正在保存...' : '💾 保存配置' }}
            </button>
          </div>
        </div>
      </div>

      <div class="card help-card">
        <div class="card-title">
          <span>💡</span> 配置参考
        </div>
        <div class="help-content">
          <div class="help-item">
            <strong>NVIDIA NIM</strong>
            <code>URL: https://integrate.api.nvidia.com/v1/chat/completions</code>
            <code>Model: meta/llama-3.1-70b-instruct</code>
          </div>
          <div class="help-item">
            <strong>DeepSeek (官方)</strong>
            <code>URL: https://api.deepseek.com/chat/completions</code>
            <code>Model: deepseek-chat</code>
          </div>
          <div class="help-item">
            <strong>硅基流动 (SiliconFlow)</strong>
            <code>URL: https://api.siliconflow.cn/v1/chat/completions</code>
            <code>Model: deepseek-ai/DeepSeek-V3</code>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { listSettings, saveLLMSettings, clearSetting, testLLMConnection } from '@/api'

interface SettingsForm {
  LLM_API_URL: string
  LLM_API_KEY: string
  LLM_MODEL: string
}

const form = ref<SettingsForm>({
  LLM_API_URL: '',
  LLM_API_KEY: '',
  LLM_MODEL: '',
})

const showKey = ref(false)
const saving = ref(false)
const testing = ref(false)
const hasStoredKey = ref(false)
const loadingSettings = ref(true)
const settingsLoaded = ref(false)
let active = true
let draftGeneration = 0
let testRequestId = 0
const saveStatus = ref<{ type: 'success' | 'error', msg: string } | null>(null)

// Record all edits synchronously so changing a value back cannot revive an old test.
watch(() => [form.value.LLM_API_URL, form.value.LLM_API_KEY, form.value.LLM_MODEL, hasStoredKey.value], () => {
  draftGeneration += 1
  testRequestId += 1
  testing.value = false
  saveStatus.value = null
}, { flush: 'sync' })

onUnmounted(() => { active = false; testRequestId += 1 })

function errorMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string' && detail.message.trim()) return detail.message
  return fallback
}

onMounted(async () => {
  try {
    const settings = await listSettings()
    if (!active) return
    settings.forEach(s => {
      if (s.key === 'LLM_API_URL' || s.key === 'LLM_MODEL') {
        form.value[s.key] = s.value
      }
      if (s.key === 'LLM_API_KEY') {
        hasStoredKey.value = Boolean(s.is_configured)
      }
    })
    settingsLoaded.value = true
  } catch (e) {
    if (active) saveStatus.value = { type: 'error', msg: errorMessage(e, '加载设置失败，请重新打开重试。') }
  } finally {
    if (active) loadingSettings.value = false
  }
})

async function saveSettings() {
  if (saving.value || testing.value || loadingSettings.value || !settingsLoaded.value) return
  const generation = draftGeneration
  const submittedKey = form.value.LLM_API_KEY.trim()
  const payload = {
    api_url: form.value.LLM_API_URL.trim(),
    model: form.value.LLM_MODEL.trim(),
    ...(submittedKey ? { api_key: submittedKey } : {}),
  }
  saving.value = true
  saveStatus.value = null
  try {
    const settings = await saveLLMSettings(payload)
    if (!active) return
    const unchanged = generation === draftGeneration
    const savedKey = settings.find(setting => setting.key === 'LLM_API_KEY')
    if (savedKey) hasStoredKey.value = Boolean(savedKey.is_configured)
    if (unchanged && submittedKey) form.value.LLM_API_KEY = ''
    saveStatus.value = { type: 'success', msg: unchanged ? '设置保存成功！' : '已保存提交的配置，当前修改尚未保存。' }
  } catch (e) {
    if (active) saveStatus.value = { type: 'error', msg: errorMessage(e, '保存失败，请检查网络或后端服务。') }
  } finally {
    saving.value = false
  }
}

async function clearApiKey() {
  if (saving.value || testing.value || loadingSettings.value || !settingsLoaded.value) return
  const generation = draftGeneration
  saving.value = true
  saveStatus.value = null
  try {
    await clearSetting('LLM_API_KEY')
    if (!active) return
    const unchanged = generation === draftGeneration
    hasStoredKey.value = false
    if (unchanged) form.value.LLM_API_KEY = ''
    saveStatus.value = { type: 'success', msg: 'API Key 已清空。' }
  } catch (e) {
    if (active) saveStatus.value = { type: 'error', msg: errorMessage(e, '清空失败，请检查网络或后端服务。') }
  } finally {
    saving.value = false
  }
}

async function testConnection() {
  if (testing.value || saving.value || loadingSettings.value || !settingsLoaded.value) return
  const generation = draftGeneration
  const request = ++testRequestId
  const payload = {
    api_url: form.value.LLM_API_URL.trim(),
    api_key: form.value.LLM_API_KEY.trim() || (hasStoredKey.value ? '__use_saved__' : ''),
    model: form.value.LLM_MODEL.trim(),
  }
  const isCurrent = () => active && generation === draftGeneration && request === testRequestId
  testing.value = true
  saveStatus.value = null
  try {
    const result = await testLLMConnection(payload)
    if (!isCurrent()) return
    saveStatus.value = { type: result.success ? 'success' : 'error', msg: result.message }
  } catch (e) {
    if (!isCurrent()) return
    saveStatus.value = { type: 'error', msg: errorMessage(e, '模型测试请求失败，请检查后端服务。') }
  } finally {
    if (isCurrent()) testing.value = false
  }
}
</script>

<style scoped>
.settings-view {
  max-width: 1000px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 28px;
}

.page-header h1 {
  font-size: 22px;
  font-weight: 700;
  margin-bottom: 8px;
}

.page-desc {
  font-size: 14px;
  color: var(--text-secondary);
}

.settings-container {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 24px;
}

.settings-form {
  padding: 12px 0;
}

.form-item {
  margin-bottom: 20px;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.input-wrapper {
  position: relative;
  display: flex;
}

.form-input {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  font-size: 14px;
  background: var(--bg-primary);
  transition: all 0.2s;
  outline: none;
}

.form-input:focus {
  border-color: var(--accent);
  background: #fff;
  box-shadow: 0 0 0 3px var(--accent-light);
}

.btn-toggle-eye {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  opacity: 0.6;
}

.btn-toggle-eye:hover {
  opacity: 1;
}

.form-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 6px;
}

.btn-text {
  margin-top: 8px;
  padding: 0;
  border: none;
  background: none;
  color: var(--danger);
  cursor: pointer;
  font-size: 12px;
}

.btn-text:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.form-footer {
  margin-top: 32px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-top: 1px solid var(--border-light);
  padding-top: 24px;
}

.status-msg {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
}

.status-msg.success { color: #059669; }
.status-msg.error { color: #dc2626; }

.help-card {
  height: fit-content;
}

.help-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.help-item {
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-light);
}

.help-item:last-child {
  border-bottom: none;
}

.help-item strong {
  display: block;
  font-size: 13px;
  margin-bottom: 8px;
  color: var(--text-primary);
}

.help-item code {
  display: block;
  font-family: var(--font-mono);
  font-size: 12px;
  background: #f1f5f9;
  padding: 4px 8px;
  border-radius: 4px;
  margin-top: 4px;
  word-break: break-all;
  color: #475569;
}

@media (max-width: 800px) {
  .settings-container {
    grid-template-columns: 1fr;
  }
}
</style>
