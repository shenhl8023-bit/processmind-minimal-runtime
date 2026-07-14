<template>
  <el-dialog
    v-model="visible"
    width="480px"
    class="premium-settings-dialog"
    :show-close="false"
    :align-center="true"
    destroy-on-close
  >
    <template #header>
      <div class="p-dialog-header">
        <div class="p-header-info">
          <div class="p-header-icon-box">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" class="p-icon-gradient-svg">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
              <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
              <line x1="12" y1="22.08" x2="12" y2="12"></line>
            </svg>
          </div>
          <div class="p-header-texts">
            <h2 class="p-dialog-title">系统模型配置</h2>
            <p class="p-dialog-subtitle">配置用于分析和提取的语言模型接口</p>
          </div>
        </div>
        <button class="p-btn-close" title="关闭" @click="handleClose">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>
    </template>

    <div class="p-dialog-body">
      <!-- Preset Templates -->
      <div class="p-preset-section">
        <label class="p-label">快速配置</label>
        <div class="p-preset-buttons">
          <button
            v-for="preset in presets"
            :key="preset.key"
            class="p-preset-btn"
            :class="{ active: activePreset === preset.key }"
            @click="applyPreset(preset)"
            type="button"
          >
            {{ preset.label }}
          </button>
        </div>
      </div>

      <div class="p-settings-form">
        <!-- API URL -->
        <div class="p-field">
          <label class="p-label">API 基础路径 <span class="p-required">*</span></label>
          <div class="p-input-wrapper">
            <input
              v-model="form.LLM_API_URL"
              type="text"
              placeholder="https://api.deepseek.com/v1"
              :class="{ 'has-error': errors.LLM_API_URL }"
              @blur="validateField('LLM_API_URL')"
            />
          </div>
          <p v-if="errors.LLM_API_URL" class="p-error">{{ errors.LLM_API_URL }}</p>
          <p v-else class="p-hint">完整的 API 端点地址，例如 https://api.deepseek.com/v1</p>
        </div>

        <!-- API Key -->
        <div class="p-field">
          <label class="p-label">API Key <span class="p-required">*</span></label>
          <div class="p-input-wrapper p-input-with-action">
            <input
              v-model="form.LLM_API_KEY"
              :type="showKey ? 'text' : 'password'"
              :placeholder="keyConfigured ? '•••••••• (留空保持不变)' : 'sk-...'"
              :class="{ 'has-error': errors.LLM_API_KEY }"
              @blur="validateField('LLM_API_KEY')"
            />
            <button class="p-input-action" @click="showKey = !showKey" type="button">
              <svg v-if="showKey" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
                <line x1="1" y1="1" x2="23" y2="23"></line>
              </svg>
              <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                <circle cx="12" cy="12" r="3"></circle>
              </svg>
            </button>
          </div>
          <p v-if="errors.LLM_API_KEY" class="p-error">{{ errors.LLM_API_KEY }}</p>
          <p v-else-if="keyConfigured" class="p-hint p-hint-success">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            已配置密钥，输入新值可更新
          </p>
        </div>

        <!-- Model Selection -->
        <div class="p-field">
          <label class="p-label">默认模型 <span class="p-required">*</span></label>
          <div class="p-model-row">
            <div class="p-input-wrapper p-input-flex">
              <input
                v-model="form.LLM_MODEL"
                type="text"
                list="model-suggestions"
                placeholder="deepseek-chat"
                :class="{ 'has-error': errors.LLM_MODEL }"
                @blur="validateField('LLM_MODEL')"
              />
              <datalist id="model-suggestions">
                <option v-for="m in availableModels" :key="m.id" :value="m.id">
                  {{ m.name }}
                </option>
              </datalist>
            </div>
            <button
              class="p-btn-icon-only"
              @click="fetchModels"
              :disabled="loadingModels || testing || saving"
              title="获取模型列表"
              type="button"
            >
              <span v-if="loadingModels" class="p-spin">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="2" x2="12" y2="6"></line><line x1="12" y1="18" x2="12" y2="22"></line><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line><line x1="2" y1="12" x2="6" y2="12"></line><line x1="18" y1="12" x2="22" y2="12"></line><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line></svg>
              </span>
              <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="23 4 23 10 17 10"></polyline>
                <polyline points="1 20 1 14 7 14"></polyline>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
              </svg>
            </button>
          </div>
          <p v-if="errors.LLM_MODEL" class="p-error">{{ errors.LLM_MODEL }}</p>
          <p v-else-if="availableModels.length > 0" class="p-hint">
            已获取 {{ availableModels.length }} 个可用模型，点击输入框可查看建议
          </p>
          <p v-else class="p-hint">常用模型：deepseek-chat、gpt-4o、qwen-plus</p>
        </div>
      </div>

      <!-- Help Strip -->
      <div class="p-help-strip">
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="p-help-icon">
          <circle cx="12" cy="12" r="10"></circle>
          <path d="M12 16v-4"></path>
          <path d="M12 8h.01"></path>
        </svg>
        <span class="p-help-text">支持任意 OpenAI 兼容接口（如 DeepSeek、硅基流动、NVIDIA NIM 等）</span>
      </div>
    </div>

    <template #footer>
      <div class="p-dialog-footer">
        <div class="p-footer-left">
          <transition name="fade">
            <div v-if="saveStatus" :class="['p-status-indicator', saveStatus.type]">
              <span class="p-status-dot"></span>
              <span class="p-status-text">{{ saveStatus.msg }}</span>
            </div>
          </transition>
        </div>

        <div class="p-footer-right">
          <button class="p-btn-plain" @click="handleClose" type="button">取消</button>
          <button class="p-btn-outline" @click="testConnection" :disabled="testing || saving || loadingModels" type="button">
            <span v-if="testing" class="p-spin">
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="2" x2="12" y2="6"></line><line x1="12" y1="18" x2="12" y2="22"></line><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line><line x1="2" y1="12" x2="6" y2="12"></line><line x1="18" y1="12" x2="22" y2="12"></line><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line></svg>
            </span>
            <span v-else class="p-btn-icon">
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
            </span>
            测试连接
          </button>
          <button class="p-btn-primary" @click="saveSettings" :disabled="saving || testing || loadingModels" type="button">
            <span v-if="saving" class="p-spin">
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="2" x2="12" y2="6"></line><line x1="12" y1="18" x2="12" y2="22"></line><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line><line x1="2" y1="12" x2="6" y2="12"></line><line x1="18" y1="12" x2="22" y2="12"></line><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line></svg>
            </span>
            保存设置
          </button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { listSettings, updateSetting, testLLMConnection, getAvailableModels } from '@/api'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const visible = ref(false)
const showKey = ref(false)
const saving = ref(false)
const testing = ref(false)
const loadingModels = ref(false)
const keyConfigured = ref(false)
const activePreset = ref<string | null>(null)
const saveStatus = ref<{ type: 'success' | 'error', msg: string } | null>(null)
const availableModels = ref<{ id: string; name: string }[]>([])

interface SettingsForm {
  LLM_API_URL: string
  LLM_API_KEY: string
  LLM_MODEL: string
}

interface FormErrors {
  LLM_API_URL: string
  LLM_API_KEY: string
  LLM_MODEL: string
}

const form = ref<SettingsForm>({
  LLM_API_URL: '',
  LLM_API_KEY: '',
  LLM_MODEL: '',
})

const errors = ref<FormErrors>({
  LLM_API_URL: '',
  LLM_API_KEY: '',
  LLM_MODEL: '',
})

const presets = [
  { key: 'deepseek', label: 'DeepSeek', url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  { key: 'openai', label: 'OpenAI', url: 'https://api.openai.com/v1', model: 'gpt-4o' },
  { key: 'dashscope', label: '通义千问', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  { key: 'siliconflow', label: '硅基流动', url: 'https://api.siliconflow.cn/v1', model: 'deepseek-ai/DeepSeek-V3' },
]

watch(() => props.modelValue, async (val) => {
  visible.value = val
  if (val) {
    await loadSettings()
  }
})

watch(visible, (val) => {
  emit('update:modelValue', val)
})

function validateField(field: keyof FormErrors) {
  if (field === 'LLM_API_URL') {
    if (!form.value.LLM_API_URL.trim()) {
      errors.value.LLM_API_URL = '请输入 API 地址'
    } else if (!/^https?:\/\/.+/.test(form.value.LLM_API_URL.trim())) {
      errors.value.LLM_API_URL = '请输入有效的 URL 地址'
    } else {
      errors.value.LLM_API_URL = ''
    }
  }

  if (field === 'LLM_API_KEY') {
    if (!keyConfigured.value && !form.value.LLM_API_KEY.trim()) {
      errors.value.LLM_API_KEY = '请输入 API Key'
    } else {
      errors.value.LLM_API_KEY = ''
    }
  }

  if (field === 'LLM_MODEL') {
    if (!form.value.LLM_MODEL.trim()) {
      errors.value.LLM_MODEL = '请输入模型名称'
    } else {
      errors.value.LLM_MODEL = ''
    }
  }
}

function validateAll(): boolean {
  validateField('LLM_API_URL')
  validateField('LLM_API_KEY')
  validateField('LLM_MODEL')
  return !errors.value.LLM_API_URL && !errors.value.LLM_API_KEY && !errors.value.LLM_MODEL
}

function applyPreset(preset: typeof presets[0]) {
  form.value.LLM_API_URL = preset.url
  form.value.LLM_MODEL = preset.model
  activePreset.value = preset.key
  errors.value.LLM_API_URL = ''
  errors.value.LLM_MODEL = ''
}

async function loadSettings() {
  try {
    const settings = await listSettings()
    settings.forEach(s => {
      if (s.key in form.value) {
        form.value[s.key as keyof SettingsForm] = s.value
      }
      if (s.key === 'LLM_API_KEY') {
        keyConfigured.value = !!s.is_configured
      }
    })

    // 自动获取可用模型
    if (form.value.LLM_API_URL && keyConfigured.value) {
      await fetchModels()
    }
  } catch (e) {
    console.error('加载设置失败', e)
  }
}

async function fetchModels() {
  loadingModels.value = true
  try {
    const models = await getAvailableModels()
    availableModels.value = models
    if (models.length > 0) {
      saveStatus.value = { type: 'success', msg: `获取到 ${models.length} 个可用模型` }
      setTimeout(() => { saveStatus.value = null }, 2000)
    } else {
      saveStatus.value = { type: 'error', msg: '未获取到模型列表，请检查配置后手动输入' }
      setTimeout(() => { saveStatus.value = null }, 3000)
    }
  } catch (e) {
    console.error('获取模型列表失败', e)
    saveStatus.value = { type: 'error', msg: '获取模型列表失败' }
    setTimeout(() => { saveStatus.value = null }, 3000)
  } finally {
    loadingModels.value = false
  }
}

async function saveSettings() {
  if (!validateAll()) {
    return
  }

  saving.value = true
  saveStatus.value = null
  try {
    const tasks = [
      updateSetting('LLM_API_URL', form.value.LLM_API_URL.trim()),
      updateSetting('LLM_MODEL', form.value.LLM_MODEL.trim()),
    ]
    // 密钥字段为空时不发送，避免覆盖已有值
    if (form.value.LLM_API_KEY.trim()) {
      tasks.push(updateSetting('LLM_API_KEY', form.value.LLM_API_KEY.trim()))
    }
    await Promise.all(tasks)
    saveStatus.value = { type: 'success', msg: '设置已保存' }
    setTimeout(() => { saveStatus.value = null; visible.value = false }, 1500)
  } catch (e) {
    console.error('保存设置失败', e)
    saveStatus.value = { type: 'error', msg: '保存失败，请检查网络' }
  } finally {
    saving.value = false
  }
}

async function testConnection() {
  if (!validateAll()) {
    return
  }

  testing.value = true
  saveStatus.value = null
  try {
    // 使用用户输入的配置进行测试，如果 API Key 为空且已配置，则使用已保存的密钥
    let apiKey = form.value.LLM_API_KEY.trim()
    if (!apiKey && keyConfigured.value) {
      // 需要先保存其他配置，然后使用已保存的密钥测试
      await updateSetting('LLM_API_URL', form.value.LLM_API_URL.trim())
      await updateSetting('LLM_MODEL', form.value.LLM_MODEL.trim())
      const result = await testLLMConnection({
        api_url: form.value.LLM_API_URL.trim(),
        api_key: '__use_saved__',
        model: form.value.LLM_MODEL.trim(),
      })
      saveStatus.value = {
        type: result.success ? 'success' : 'error',
        msg: result.message,
      }
    } else {
      const result = await testLLMConnection({
        api_url: form.value.LLM_API_URL.trim(),
        api_key: apiKey,
        model: form.value.LLM_MODEL.trim(),
      })
      saveStatus.value = {
        type: result.success ? 'success' : 'error',
        msg: result.message,
      }
    }
    setTimeout(() => { saveStatus.value = null }, 3000)
  } catch (e) {
    console.error('测试连接失败', e)
    saveStatus.value = { type: 'error', msg: '测试请求失败' }
  } finally {
    testing.value = false
  }
}

function handleClose() {
  visible.value = false
}
</script>

<style scoped>
/* Typography & Reset */
.p-dialog-header {
  padding: 16px 20px 12px;
  border-bottom: 1px solid #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.p-header-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.p-header-icon-box {
  width: 32px;
  height: 32px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.05), rgba(99, 102, 241, 0.12));
  border: 1px solid rgba(99, 102, 241, 0.15);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6366f1;
}

.p-icon-gradient-svg {
  filter: drop-shadow(0 2px 4px rgba(99, 102, 241, 0.15));
}

.p-dialog-title {
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
  letter-spacing: -0.01em;
  margin: 0;
  line-height: 1.2;
}

.p-dialog-subtitle {
  font-size: 11px;
  color: #64748b;
  margin-top: 3px;
  margin-bottom: 0;
  line-height: 1.2;
}

.p-btn-close {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.p-btn-close:hover {
  background: #f1f5f9;
  color: #475569;
}

.p-dialog-body {
  padding: 16px 20px;
}

/* Preset Section */
.p-preset-section {
  margin-bottom: 16px;
}

.p-preset-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.p-preset-btn {
  padding: 6px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #ffffff;
  color: #475569;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.p-preset-btn:hover {
  border-color: #6366f1;
  color: #6366f1;
  background: #f8fafc;
}

.p-preset-btn.active {
  border-color: #6366f1;
  background: rgba(99, 102, 241, 0.08);
  color: #6366f1;
}

.p-settings-form {
  display: flex;
  flex-direction: column;
}

.p-field {
  margin-bottom: 14px;
}

.p-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: #334155;
  margin-bottom: 6px;
}

.p-required {
  color: #ef4444;
  margin-left: 2px;
}

.p-input-wrapper {
  position: relative;
}

.p-input-wrapper input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 13px;
  color: #0f172a;
  background: #f8fafc;
  transition: all 0.2s ease;
  outline: none;
  font-family: inherit;
  box-sizing: border-box;
}

.p-input-wrapper input::placeholder {
  color: #94a3b8;
}

.p-input-wrapper input:hover {
  border-color: #cbd5e1;
}

.p-input-wrapper input:focus {
  border-color: #6366f1;
  background: #ffffff;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.08), 0 1px 2px rgba(0,0,0,0.05);
}

.p-input-wrapper input.has-error {
  border-color: #ef4444;
  background: #fef2f2;
}

.p-input-wrapper input.has-error:focus {
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.08);
}

.p-input-with-action input {
  padding-right: 40px;
}

.p-input-action {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  background: transparent;
  border: none;
  border-radius: 4px;
  padding: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
  color: #64748b;
  display: flex;
  align-items: center;
  justify-content: center;
}

.p-input-action:hover {
  background: #e2e8f0;
  color: #0f172a;
}

.p-model-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.p-input-flex {
  flex: 1;
}

.p-btn-icon-only {
  width: 34px;
  height: 34px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
  color: #64748b;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.p-btn-icon-only:hover:not(:disabled) {
  border-color: #6366f1;
  color: #6366f1;
  background: #f8fafc;
}

.p-btn-icon-only:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.p-hint {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 4px;
  margin-bottom: 0;
  line-height: 1.4;
  display: block;
}

.p-error {
  font-size: 11px;
  color: #ef4444;
  margin-top: 4px;
  margin-bottom: 0;
  line-height: 1.4;
  display: block;
}

.p-hint-success {
  color: #059669;
  display: flex;
  align-items: center;
  gap: 4px;
}

.p-help-strip {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  color: #475569;
}

.p-help-icon {
  flex-shrink: 0;
  color: #6366f1;
}
.p-help-text {
  font-size: 11px;
  font-weight: 500;
  line-height: 1.4;
  color: #475569;
}

.p-dialog-footer {
  padding: 12px 20px;
  border-top: 1px solid #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #f8fafc;
}

.p-footer-left {
  display: flex;
  align-items: center;
  min-height: 24px;
}

.p-footer-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.p-status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
}
.p-status-indicator.success { color: #059669; }
.p-status-indicator.error { color: #dc2626; }

.p-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.p-status-text {
  font-size: 12px;
  font-weight: 500;
}

.p-btn-plain {
  background: transparent;
  border: 1px solid transparent;
  color: #64748b;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 6px;
  transition: all 0.2s ease;
}
.p-btn-plain:hover {
  background: #e2e8f0;
  color: #1e293b;
}

.p-btn-outline {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  color: #334155;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 6px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}
.p-btn-outline:hover:not(:disabled) { background: #f8fafc; border-color: #cbd5e1; color: #0f172a; }
.p-btn-outline:disabled {
  background: #f1f5f9;
  color: #94a3b8;
  border-color: #e2e8f0;
  cursor: not-allowed;
  box-shadow: none;
}
.p-btn-icon {
  display: inline-flex;
  align-items: center;
  color: #64748b;
}
.p-btn-outline:hover:not(:disabled) .p-btn-icon {
  color: #475569;
}

.p-btn-primary {
  background: linear-gradient(135deg, #4f46e5, #4338ca);
  color: #ffffff;
  border: none;
  padding: 6px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  align-items: center;
  gap: 6px;
  box-shadow: 0 1px 2px rgba(79, 70, 229, 0.2), inset 0 1px 0 rgba(255,255,255,0.1);
}
.p-btn-primary:hover:not(:disabled) {
  background: linear-gradient(135deg, #4338ca, #3730a3);
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.25);
}
.p-btn-primary:active:not(:disabled) {
  transform: scale(0.98);
}
.p-btn-primary:disabled {
  background: #f1f5f9;
  color: #94a3b8;
  box-shadow: none;
  cursor: not-allowed;
}

.p-spin {
  display: inline-flex;
  animation: rotate 1.5s linear infinite;
}

@keyframes rotate { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

:deep(.el-overlay) {
  background-color: rgba(15, 23, 42, 0.4) !important;
  backdrop-filter: blur(6px);
}

:deep(.el-dialog) {
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 20px 40px -10px rgba(0, 0, 0, 0.12), 0 0 0 1px rgba(0, 0, 0, 0.04);
  padding: 0;
}

:deep(.el-dialog__header), :deep(.el-dialog__footer) {
  padding: 0;
}

/* Transition styles */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>
