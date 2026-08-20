<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Check, Eye, EyeOff, HardDrive, Image as ImageIcon, KeyRound, LogOut, RefreshCw, Save, ServerCog, Trash2, Upload } from 'lucide-vue-next'
import { apiDelete, apiGet, apiPut, apiPutFile, apiUrl } from '../api'
import { logout } from '../auth'
import { appConfig, loadAppBranding } from '../appConfig'
import FloatingToast from '../components/FloatingToast.vue'
import CookieView from './CookieView.vue'

interface SettingField {
  key: string
  group: string
  label: string
  type: 'string' | 'integer' | 'boolean' | 'secret' | 'password' | 'url' | 'select' | 'multiline'
  value: unknown
  configured: boolean
  sensitive: boolean
  restart: 'none' | 'voice' | 'backend'
  minimum: number | null
  maximum: number | null
  options: string[]
  help: string
}

interface SettingsPayload {
  fields: SettingField[]
  assets: ManagedAsset[]
  bootstrap: Record<string, unknown>
  voice_restart_requested?: boolean
  voice_config_revision?: string
  backend_restart_required?: boolean
  apply_pending?: boolean
}

interface ManagedAsset {
  key: string
  group: string
  label: string
  configured: boolean
  url: string
  version: number
  restart: 'none' | 'voice'
  accept: string
  max_size_mb: number
  storage_path: string
  help: string
}

interface CacheStatus {
  total_bytes: number
  total_files: number
  bilibili_audio: {
    file_count: number
    size_bytes: number
  }
  memory_entries: {
    bilibili_view_summaries: number
    bilibili_subtitles: number
  }
}

interface CacheClearResult extends CacheStatus {
  ok: boolean
  removed_files: number
  removed_bytes: number
  skipped_files: number
  skipped_bytes: number
  cleared_memory_entries: number
}

const GROUPS = [
  ['web', 'Web 配置'],
  ['backend', 'Voice 服务'],
  ['music', '音乐接口配置'],
  ['cache', '缓存'],
  ['authorization', '音乐会员登录'],
  ['teamspeak', 'TeamSpeak 配置'],
  ['serverquery', 'ServerQuery 兼容'],
  ['access', '外部 api'],
] as const

const MUSIC_SETTING_KEYS = new Set([
  'backend.bilibili_max_duration_minutes',
  'backend.bilibili_audio_cache_ttl_hours',
  'backend.bilibili_audio_cache_max_mb',
  'backend.bilibili_audio_partial_ttl_minutes',
])

const GROUP_ALIASES: Record<string, string> = {
  description: 'teamspeak',
  voice: 'backend',
}

const router = useRouter()
const route = useRoute()
const payload = ref<SettingsPayload | null>(null)
const rawRequestedGroup = String(route.query.group || '')
const requestedGroup = GROUP_ALIASES[rawRequestedGroup] || rawRequestedGroup
const activeGroup = ref(GROUPS.some((group) => group[0] === requestedGroup) ? requestedGroup : 'web')
const draft = ref<Record<string, any>>({})
const revealed = ref<Record<string, boolean>>({})
const assetBusy = ref<Record<string, boolean>>({})
const loading = ref(true)
const saving = ref(false)
const applying = ref(false)
const cacheLoading = ref(false)
const cacheClearing = ref(false)
const cacheStatus = ref<CacheStatus | null>(null)
const cacheError = ref('')
const error = ref('')
const toastMessage = ref('')
const toastType = ref<'success' | 'error' | 'info'>('info')
let toastTimer: ReturnType<typeof setTimeout> | null = null
let waitGeneration = 0

const activeFields = computed(() => payload.value?.fields.filter((field) => (
  field.group === activeGroup.value
  && (field.group !== 'music' || MUSIC_SETTING_KEYS.has(field.key))
)) || [])
const activeAssets = computed(() => payload.value?.assets.filter((asset) => asset.group === activeGroup.value) || [])
const activeNeedsVoiceRestart = computed(() => (
  activeFields.value.some((field) => field.restart === 'voice')
  || activeAssets.value.some((asset) => asset.restart === 'voice')
))
const memoryCacheEntryCount = computed(() => {
  const entries = cacheStatus.value?.memory_entries
  return Number(entries?.bilibili_view_summaries || 0) + Number(entries?.bilibili_subtitles || 0)
})

function hydrate(result: SettingsPayload) {
  payload.value = result
  const next: Record<string, any> = {}
  for (const field of result.fields) {
    next[field.key] = field.sensitive ? '' : field.value
  }
  draft.value = next
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    hydrate(await apiGet<SettingsPayload>('/admin/settings'))
  } catch (e: any) {
    error.value = String(e?.message || e)
    showToast(error.value, 'error', 8000)
  } finally {
    loading.value = false
  }
  if (activeGroup.value === 'cache') await loadCacheStatus()
}

function showToast(message: string, type: 'success' | 'error' | 'info', duration = 4500) {
  if (toastTimer) clearTimeout(toastTimer)
  toastMessage.value = message
  toastType.value = type
  if (duration > 0) {
    toastTimer = setTimeout(() => {
      toastMessage.value = ''
      toastTimer = null
    }, duration)
  }
}

function closeToast() {
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = null
  toastMessage.value = ''
}

function delay(milliseconds: number) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds))
}

async function waitForVoiceRevision(revision: string, timeoutMs = 60000) {
  const generation = ++waitGeneration
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline && generation === waitGeneration) {
    try {
      const status = await apiGet<{ voice_connected?: boolean; voice_config_revision?: string }>('/voice/status')
      if (status.voice_connected && status.voice_config_revision === revision) return
    } catch {
      // A short connection failure is expected while Voice is restarting.
    }
    await delay(1000)
  }
  if (generation !== waitGeneration) throw new Error('等待已取消')
  throw new Error('Voice 未在 60 秒内恢复，请检查 Voice 服务日志')
}

async function persistSettings(apply: boolean) {
  if (apply) applying.value = true
  else saving.value = true
  error.value = ''
  try {
    const result = await apiPut<SettingsPayload>('/admin/settings', { values: draft.value, apply })
    hydrate(result)
    if (!apply) {
      showToast('配置已保存', 'success')
      return
    }

    await loadAppBranding()
    if (result.voice_restart_requested && result.voice_config_revision) {
      showToast('正在等待 Voice 重启', 'info', 0)
      await waitForVoiceRevision(result.voice_config_revision)
      showToast('已重启成功', 'success')
    } else if (result.backend_restart_required) {
      showToast('配置已应用，后端服务将在下次启动时使用新配置', 'success', 6500)
    } else {
      showToast('配置已应用', 'success')
    }
  } catch (e: any) {
    error.value = String(e?.message || e)
    showToast(error.value, 'error', 8000)
  } finally {
    if (apply) applying.value = false
    else saving.value = false
  }
}

async function saveConfig() {
  await persistSettings(false)
}

async function applyConfig() {
  await persistSettings(true)
}

function assetPreviewUrl(asset: ManagedAsset): string {
  if (!asset.url) return ''
  return `${apiUrl(asset.url)}?v=${asset.version}`
}

async function uploadAsset(asset: ManagedAsset, event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  assetBusy.value[asset.key] = true
  error.value = ''
  try {
    const result = await apiPutFile<{ voice_restart_requested?: boolean; voice_config_revision?: string }>(`/admin/assets/${asset.key}`, file)
    await load()
    if (asset.key === 'web-app-icon') await loadAppBranding()
    if (result.voice_restart_requested && result.voice_config_revision) {
      showToast('正在等待 Voice 重启', 'info', 0)
      await waitForVoiceRevision(result.voice_config_revision)
      showToast('已重启成功', 'success')
    } else {
      showToast('图片已上传并生效', 'success')
    }
  } catch (e: any) {
    error.value = String(e?.message || e)
    showToast(error.value, 'error', 8000)
  } finally {
    assetBusy.value[asset.key] = false
  }
}

async function clearAsset(asset: ManagedAsset) {
  assetBusy.value[asset.key] = true
  error.value = ''
  try {
    const result = await apiDelete<{ voice_restart_requested?: boolean; voice_config_revision?: string }>(`/admin/assets/${asset.key}`)
    await load()
    if (asset.key === 'web-app-icon') await loadAppBranding()
    if (result.voice_restart_requested && result.voice_config_revision) {
      showToast('正在等待 Voice 重启', 'info', 0)
      await waitForVoiceRevision(result.voice_config_revision)
      showToast('已重启成功', 'success')
    } else {
      showToast('图片已清除', 'success')
    }
  } catch (e: any) {
    error.value = String(e?.message || e)
    showToast(error.value, 'error', 8000)
  } finally {
    assetBusy.value[asset.key] = false
  }
}

function clearSecret(field: SettingField) {
  draft.value[field.key] = null
  field.configured = false
}

function formatBytes(value: unknown): string {
  const bytes = Number(value)
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const size = bytes / (1024 ** index)
  return `${size.toFixed(index === 0 || size >= 10 ? 0 : 1)} ${units[index]}`
}

async function loadCacheStatus() {
  if (cacheClearing.value) return
  cacheLoading.value = true
  cacheError.value = ''
  try {
    cacheStatus.value = await apiGet<CacheStatus>('/admin/cache')
  } catch (e: any) {
    cacheError.value = String(e?.message || e)
  } finally {
    cacheLoading.value = false
  }
}

async function clearCache() {
  const usedSpace = formatBytes(cacheStatus.value?.total_bytes || 0)
  const confirmed = window.confirm(
    `确定清理缓存吗？\n\n将删除约 ${usedSpace} 的 B 站音频缓存和临时内存数据。正在播放或下载的音频会保留。`,
  )
  if (!confirmed) return

  cacheClearing.value = true
  cacheError.value = ''
  try {
    const result = await apiDelete<CacheClearResult>('/admin/cache')
    cacheStatus.value = result
    const retained = result.skipped_files > 0 ? `；保留 ${result.skipped_files} 个正在使用的文件` : ''
    showToast(`已清理 ${result.removed_files} 个文件，释放 ${formatBytes(result.removed_bytes)}${retained}`, 'success')
  } catch (e: any) {
    cacheError.value = String(e?.message || e)
    showToast(cacheError.value, 'error', 8000)
  } finally {
    cacheClearing.value = false
  }
}

function selectGroup(group: string) {
  activeGroup.value = group
  error.value = ''
  if (group === 'cache') void loadCacheStatus()
}

async function signOut() {
  await logout()
  await router.replace('/login')
}

onMounted(load)
onBeforeUnmount(() => {
  waitGeneration += 1
  if (toastTimer) clearTimeout(toastTimer)
})
</script>

<template>
  <div class="theme-settings-shell h-full flex flex-col bg-gray-50">
    <header class="theme-settings-header bg-white border-b border-gray-200 px-4 md:px-7 py-3 flex flex-wrap items-center justify-between gap-3">
      <div class="min-w-0">
        <h1 class="text-xl font-bold text-gray-900 flex items-center gap-2">
          <ServerCog :size="22" class="text-blue-600" />
          系统配置
        </h1>
        <p class="text-sm text-gray-500 mt-1">运行配置与服务连接</p>
      </div>
      <div class="ml-auto flex flex-wrap items-center justify-end gap-2">
        <template v-if="activeGroup !== 'authorization' && activeGroup !== 'cache'">
          <button class="btn-secondary settings-header-action" type="button" :disabled="loading || saving || applying" @click="saveConfig">
            <Save :size="17" />
            {{ saving ? '正在保存' : '保存配置' }}
          </button>
          <button class="btn-primary settings-header-action" type="button" :disabled="loading || saving || applying" @click="applyConfig">
            <RefreshCw :size="17" :class="applying ? 'animate-spin' : ''" />
            {{ applying ? '正在应用' : '应用配置' }}
          </button>
        </template>
        <RouterLink to="/change-password" class="p-2 text-gray-500 hover:text-blue-600" title="修改管理员密码">
          <KeyRound :size="19" />
        </RouterLink>
        <button class="p-2 text-gray-500 hover:text-red-600" title="退出管理员登录" @click="signOut">
          <LogOut :size="19" />
        </button>
      </div>
    </header>

    <div class="flex-1 min-h-0 flex flex-col md:flex-row">
      <nav class="theme-settings-nav bg-white border-b md:border-b-0 md:border-r border-gray-200 md:w-56 p-3 overflow-x-auto md:overflow-y-auto flex md:block gap-1">
        <button
          v-for="group in GROUPS"
          :key="group[0]"
          type="button"
          :class="['whitespace-nowrap w-auto md:w-full text-left px-3 py-2.5 rounded-md text-sm font-medium transition-colors', activeGroup === group[0] ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-gray-100']"
          @click="selectGroup(group[0])"
        >
          {{ group[1] }}
        </button>
      </nav>

      <main class="theme-settings-workspace flex-1 overflow-y-auto px-4 md:px-8 py-6 pb-8">
        <div class="max-w-3xl mx-auto">
          <div v-if="loading" class="py-20 text-center text-gray-500">正在加载配置...</div>
          <template v-else-if="payload">
            <div class="flex items-center justify-between mb-6">
              <h2 class="text-lg font-semibold text-gray-900">{{ GROUPS.find((item) => item[0] === activeGroup)?.[1] }}</h2>
              <span v-if="activeNeedsVoiceRestart" class="theme-settings-restart text-xs px-2 py-1 rounded bg-amber-50 text-amber-700 border border-amber-200">应用时自动重启 Voice</span>
            </div>

            <CookieView v-if="activeGroup === 'authorization'" embedded />

            <section v-if="activeGroup === 'cache'" class="theme-settings-panel bg-white border border-gray-200 rounded-lg overflow-hidden">
              <div class="p-5 md:p-6">
                <div class="flex flex-wrap items-start justify-between gap-4">
                  <div class="flex items-center gap-4">
                    <div class="w-12 h-12 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
                      <HardDrive :size="24" />
                    </div>
                    <div>
                      <p class="text-sm text-gray-500">当前可清理缓存占用</p>
                      <p class="text-3xl font-semibold text-gray-900 mt-1">
                        {{ cacheLoading && !cacheStatus ? '--' : formatBytes(cacheStatus?.total_bytes) }}
                      </p>
                      <p class="text-xs text-gray-500 mt-1">{{ cacheStatus?.total_files ?? 0 }} 个 B 站音频缓存文件</p>
                    </div>
                  </div>
                  <button type="button" class="btn-secondary" :disabled="cacheLoading || cacheClearing" @click="loadCacheStatus">
                    <RefreshCw :size="17" :class="cacheLoading ? 'animate-spin' : ''" />
                    刷新
                  </button>
                </div>

                <div v-if="cacheError" class="mt-5 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {{ cacheError }}
                </div>

                <dl class="mt-6 divide-y divide-gray-100 border-y border-gray-100">
                  <div class="flex items-center justify-between gap-4 py-3 text-sm">
                    <dt class="text-gray-600">B 站音频缓存</dt>
                    <dd class="text-right text-gray-900 font-medium">
                      {{ formatBytes(cacheStatus?.bilibili_audio?.size_bytes) }}
                      <span class="text-gray-500 font-normal">· {{ cacheStatus?.bilibili_audio?.file_count ?? 0 }} 个文件</span>
                    </dd>
                  </div>
                  <div class="flex items-center justify-between gap-4 py-3 text-sm">
                    <dt class="text-gray-600">临时内存缓存</dt>
                    <dd class="text-right text-gray-900 font-medium">{{ memoryCacheEntryCount }} 项</dd>
                  </div>
                </dl>

                <div class="mt-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                  <p class="text-xs leading-5 text-gray-500 max-w-xl">
                    仅清理 B 站下载音频和临时内存数据；不会删除数据库、播放队列、历史记录、登录凭据、上传图片或日志。正在播放或下载的音频会保留。
                  </p>
                  <button type="button" class="btn-secondary text-red-600 border-red-200 hover:bg-red-50 hover:text-red-700 shrink-0" :disabled="cacheLoading || cacheClearing" @click="clearCache">
                    <Trash2 :size="17" />
                    {{ cacheClearing ? '正在清理...' : '清理缓存' }}
                  </button>
                </div>
              </div>
            </section>

            <section v-if="activeAssets.length" class="theme-settings-panel bg-white border border-gray-200 rounded-lg divide-y divide-gray-100 mb-6">
              <div v-for="asset in activeAssets" :key="asset.key" class="p-4 md:p-5 grid md:grid-cols-[240px_minmax(0,1fr)] gap-3 md:gap-6 items-center">
                <div>
                  <div class="text-sm font-medium text-gray-800">{{ asset.label }}</div>
                  <p class="text-xs text-gray-500 mt-1">{{ asset.help }}</p>
                  <p class="text-xs text-gray-400 mt-1 font-mono break-all">{{ asset.storage_path }}</p>
                </div>
                <div class="flex flex-wrap items-center gap-3 min-w-0">
                  <div class="w-14 h-14 flex-shrink-0 border border-gray-200 rounded-md bg-gray-50 overflow-hidden flex items-center justify-center text-gray-400">
                    <img v-if="asset.configured" :src="assetPreviewUrl(asset)" :alt="asset.label" class="w-full h-full object-contain" />
                    <ImageIcon v-else :size="22" />
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="text-sm text-gray-700">{{ asset.configured ? '已上传' : '尚未上传' }}</div>
                    <div class="text-xs text-gray-500 mt-1">PNG、JPEG、WebP、GIF，最大 {{ asset.max_size_mb }} MiB</div>
                  </div>
                  <div class="flex items-center gap-2">
                    <label :class="['btn-secondary cursor-pointer', assetBusy[asset.key] ? 'opacity-50 pointer-events-none' : '']">
                      <Upload :size="17" />
                      {{ asset.configured ? '更换' : '上传' }}
                      <input type="file" class="sr-only" :accept="asset.accept" :disabled="assetBusy[asset.key]" @change="uploadAsset(asset, $event)" />
                    </label>
                    <button v-if="asset.configured" type="button" class="p-2 text-gray-500 hover:text-red-600" :disabled="assetBusy[asset.key]" title="清除图片" @click="clearAsset(asset)">
                      <Trash2 :size="18" />
                    </button>
                  </div>
                </div>
              </div>
            </section>

            <section v-if="activeFields.length" class="theme-settings-panel bg-white border border-gray-200 rounded-lg divide-y divide-gray-100">
              <div v-for="field in activeFields" :key="field.key" class="p-4 md:p-5 grid md:grid-cols-[240px_minmax(0,1fr)] gap-2 md:gap-6 items-center">
                <div>
                  <label :for="field.key" class="text-sm font-medium text-gray-800">{{ field.label }}</label>
                  <p v-if="field.help" class="text-xs text-gray-500 mt-1">{{ field.help }}</p>
                  <p v-if="field.sensitive && field.configured" class="text-xs text-green-600 mt-1 flex items-center gap-1"><Check :size="12" /> 已配置</p>
                </div>

                <label v-if="field.type === 'boolean'" class="inline-flex items-center gap-3 cursor-pointer">
                  <input v-model="draft[field.key]" type="checkbox" class="w-4 h-4 accent-blue-600" />
                  <span class="text-sm text-gray-600">{{ draft[field.key] ? '启用' : '停用' }}</span>
                </label>

                <select v-else-if="field.type === 'select'" :id="field.key" v-model="draft[field.key]" class="input-field w-full">
                  <option v-for="option in field.options" :key="option" :value="option">{{ option }}</option>
                </select>

                <textarea v-else-if="field.type === 'multiline'" :id="field.key" v-model="draft[field.key]" rows="4" class="input-field w-full resize-y" />

                <div v-else-if="field.sensitive" class="flex gap-2 min-w-0">
                  <div class="relative flex-1 min-w-0">
                    <input
                      :id="field.key"
                      v-model="draft[field.key]"
                      :type="revealed[field.key] ? 'text' : 'password'"
                      :placeholder="field.configured ? '留空表示保持当前值' : '尚未配置'"
                      autocomplete="new-password"
                      class="input-field w-full pr-10 font-mono text-sm"
                    />
                    <button type="button" class="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-700" :title="revealed[field.key] ? '隐藏' : '显示'" @click="revealed[field.key] = !revealed[field.key]">
                      <EyeOff v-if="revealed[field.key]" :size="17" />
                      <Eye v-else :size="17" />
                    </button>
                  </div>
                  <button v-if="field.configured" type="button" class="px-3 text-sm text-red-600 hover:bg-red-50 rounded-md" @click="clearSecret(field)">清除</button>
                </div>

                <input
                  v-else
                  :id="field.key"
                  v-model="draft[field.key]"
                  :type="field.type === 'integer' ? 'number' : field.type === 'url' ? 'url' : 'text'"
                  :min="field.minimum ?? undefined"
                  :max="field.maximum ?? undefined"
                  class="input-field w-full"
                />
              </div>
            </section>

            <section v-if="activeGroup === 'backend'" class="mt-6 border-t border-gray-200 pt-5">
              <h3 class="text-sm font-semibold text-gray-800 mb-3">启动配置（只读）</h3>
              <dl class="grid sm:grid-cols-2 gap-x-6 gap-y-3 text-sm">
                <div v-for="(value, key) in payload.bootstrap" :key="key" class="min-w-0">
                  <dt class="text-gray-500">{{ key }}</dt>
                  <dd class="text-gray-800 font-mono break-all mt-0.5">{{ value }}</dd>
                </div>
              </dl>
            </section>

          </template>
          <p v-if="error && !payload" class="text-red-600">{{ error }}</p>
        </div>
      </main>
    </div>
    <FloatingToast :message="toastMessage" :type="toastType" @close="closeToast" />
  </div>
</template>
