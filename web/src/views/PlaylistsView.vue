<script setup lang="ts">
import { onMounted, ref, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { onBeforeRouteLeave } from 'vue-router'
import { apiGet, apiPost } from '../api'
import { getFavoritePlaylists, toggleFavoritePlaylist } from '../utils/favorites'
import { 
  ListMusic, 
  RefreshCw, 
  AlertCircle,
  Music,
  User,
  Play,
  Heart,
  TrendingUp,
  Star
} from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'

const router = useRouter()
const error = ref('')
const status = ref('')
const loading = ref(false)
const selectedCategory = ref('热门')
const playlistKeyword = ref('热门')
const presetKeywords = ['热门', '华语', '流行', '经典', '轻音乐', '粤语', '日语', '英语']
const playlists = ref<any[]>([])
const highQualityPlaylists = ref<any[]>([])
const recommendPlaylists = ref<any[]>([])

const scrollEl = ref<HTMLElement | null>(null)
const STATE_KEY = 'tsbot:state:/playlists'

const favoritePlaylistIds = ref<Set<number>>(new Set())

function refreshFavoritePlaylistIds() {
  favoritePlaylistIds.value = new Set(getFavoritePlaylists().map((p) => Number(p.id)))
}

function isLocalFavPlaylist(id: number | string): boolean {
  const n = Number(id)
  if (!Number.isFinite(n) || n <= 0) return false
  return favoritePlaylistIds.value.has(n)
}

function toggleLocalFavPlaylist(pl: any) {
  toggleFavoritePlaylist(pl)
  refreshFavoritePlaylistIds()
}

async function loadPlaylists(cat: string = '热门') {
  loading.value = true
  error.value = ''
  const query = (cat || playlistKeyword.value || '热门').trim() || '热门'
  playlistKeyword.value = query
  selectedCategory.value = query
  
  try {
    const res = await apiGet<any>(`/qqmusic/search/playlists?keywords=${encodeURIComponent(query)}&limit=30&page=1`)
    playlists.value = (res?.playlists || []).map((playlist: any) => ({
      id: Number(playlist.id),
      source: 'qqmusic',
      name: String(playlist.name || playlist.id),
      coverImgUrl: String(playlist.cover_url || ''),
      playCount: Number(playlist.play_count || 0),
      creator: { nickname: String(playlist.creator || '') },
      trackCount: String(playlist.track_count || ''),
    }))
    highQualityPlaylists.value = []
    recommendPlaylists.value = []
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  } finally {
    loading.value = false
  }
}

async function selectCategory(cat: string) {
  selectedCategory.value = cat
  playlistKeyword.value = cat
  await loadPlaylists(cat)
}

function goToPlaylist(id: number | string) {
  saveState()
  router.push(`/playlist/${id}`)
}

function saveState() {
  const el = scrollEl.value
  if (!el) return
  sessionStorage.setItem(
    STATE_KEY,
    JSON.stringify({
      category: selectedCategory.value,
      scrollTop: el.scrollTop || 0,
    }),
  )
}

function loadSavedState(): { category?: string; scrollTop?: number } {
  try {
    const raw = sessionStorage.getItem(STATE_KEY)
    if (!raw) return {}
    const obj = JSON.parse(raw)
    return typeof obj === 'object' && obj ? obj : {}
  } catch {
    return {}
  }
}

async function restoreScroll(top: number) {
  const el = scrollEl.value
  if (!el) return
  if (!Number.isFinite(top) || top <= 0) return
  await nextTick()
  el.scrollTop = top
}

onBeforeRouteLeave(() => {
  saveState()
  return true
})

async function addPlaylistToQueue(playlist: any) {
  error.value = ''
  status.value = ''
  
  try {
    const detailRes = await apiGet<any>(`/qqmusic/playlist/${playlist.id}/songs`)
    const tracks = detailRes?.songs || []
    
    if (tracks.length === 0) {
      error.value = '歌单为空或无法获取歌曲'
      return
    }

    const confirmed = confirm(
      `确定要将歌单《${playlist.name}》的全部 ${tracks.length} 首歌曲添加到播放队列吗？

歌单较大时可能需要一点时间，请耐心等待。`,
    )
    
    if (!confirmed) {
      return
    }

    let addedCount = 0
    const failed: string[] = []
    for (const [index, track] of tracks.entries()) {
      const songMid = getTrackSongMid(track)
      const title = getTrackTitle(track)
      status.value = `正在添加 ${index + 1}/${tracks.length}：${title}`
      if (!songMid) {
        failed.push(title)
        continue
      }
      try {
        await apiPost('/queue/qqmusic', {
          song_mid: songMid,
          title,
          artist: getTrackArtist(track),
          album: getTrackAlbum(track),
          album_mid: getTrackAlbumMid(track),
          cover_url: getTrackArtwork(track),
          duration_ms: getTrackDurationMs(track),
          quality: '320',
          play_now: false,
        })
        addedCount++
      } catch {
        failed.push(title)
      }
    }

    if (failed.length > 0) {
      error.value = `有 ${failed.length} 首歌曲添加失败：${failed.slice(0, 3).join('、')}${failed.length > 3 ? ' 等' : ''}`
    }

    status.value = failed.length > 0
      ? `已添加 ${addedCount} 首歌曲到播放队列，${failed.length} 首失败`
      : `已添加 ${addedCount} 首歌曲到播放队列`
    setTimeout(() => {
      status.value = ''
    }, 5000)
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

function getTrackArtist(track: any): string {
  const artists = track?.singer || track?.artists || track?.artist
  if (Array.isArray(artists)) {
    return artists.map((artist: any) => artist?.name || artist).filter(Boolean).join(', ')
  }
  return String(artists || '').trim()
}

function getTrackSongMid(track: any): string {
  return String(track?.mid || track?.songmid || track?.song_mid || '').trim()
}

function getTrackTitle(track: any): string {
  return String(
    track?.name ||
    track?.songname ||
    track?.title ||
    track?.songorig ||
    getTrackSongMid(track) ||
    '未知歌曲',
  ).trim()
}

function getTrackAlbum(track: any): string {
  return String(track?.album?.name || track?.album?.title || track?.albumname || track?.album || '').trim()
}

function getTrackAlbumMid(track: any): string {
  return String(track?.album?.mid || track?.albummid || track?.album_mid || '').trim()
}

function getTrackArtwork(track: any): string {
  const albumMid = getTrackAlbumMid(track)
  return albumMid ? `https://y.gtimg.cn/music/photo_new/T002R300x300M000${albumMid}.jpg` : ''
}

function getTrackDurationMs(track: any): number | undefined {
  const interval = Number(track?.interval)
  if (Number.isFinite(interval) && interval > 0) return interval * 1000
  const duration = Number(track?.duration_ms ?? track?.duration)
  return Number.isFinite(duration) && duration > 0 ? (duration > 1000 ? duration : duration * 1000) : undefined
}

function formatPlayCount(count: number): string {
  if (count >= 100000000) {
    return `${(count / 100000000).toFixed(1)}亿`
  } else if (count >= 10000) {
    return `${(count / 10000).toFixed(1)}万`
  }
  return count.toString()
}

onMounted(() => {
  void (async () => {
    const saved = loadSavedState()
    const savedCategory = typeof saved.category === 'string' && saved.category ? saved.category : '热门'
    selectedCategory.value = savedCategory
    playlistKeyword.value = savedCategory

    refreshFavoritePlaylistIds()
    await loadPlaylists(selectedCategory.value)
    await restoreScroll(Number(saved.scrollTop ?? 0))
  })()
})
</script>

<template>
  <div class="h-full flex flex-col bg-gray-50">
    <!-- Header -->
    <div class="bg-white/80 backdrop-blur-md border-b border-gray-200 px-6 py-4 sticky top-0 z-20 shadow-sm transition-all duration-300">
      <div class="flex items-center justify-between mb-4">
        <h1 class="text-2xl font-bold text-gray-900 flex items-center gap-3">
          <ListMusic :size="28" class="text-blue-600" />
          发现歌单
        </h1>
        <button 
          @click="loadPlaylists(selectedCategory)"
          :disabled="loading"
          class="btn-secondary text-sm py-1.5 px-3"
        >
          <RefreshCw :size="16" :class="{ 'animate-spin': loading }" />
          <span class="hidden sm:inline">刷新</span>
        </button>
      </div>
      
      <!-- QQ Music playlist search -->
      <div class="flex flex-col gap-3">
        <div class="flex gap-2">
          <input
            v-model="playlistKeyword"
            type="search"
            placeholder="搜索 QQ 音乐歌单..."
            class="flex-1 px-4 py-2 bg-gray-100 border border-gray-200 rounded-lg text-sm outline-none focus:bg-white focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            @keyup.enter="loadPlaylists(playlistKeyword)"
          />
          <button
            @click="loadPlaylists(playlistKeyword)"
            :disabled="loading || !playlistKeyword.trim()"
            class="btn-primary text-sm px-4 disabled:opacity-50"
          >
            搜索
          </button>
        </div>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="keyword in presetKeywords"
            :key="keyword"
            @click="selectCategory(keyword)"
            class="px-3 py-1 text-xs rounded-full transition-all duration-200 font-medium border"
            :class="selectedCategory === keyword
              ? 'bg-blue-600 text-white border-blue-600'
              : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50 hover:border-gray-300'"
          >
            {{ keyword }}
          </button>
        </div>
      </div>
    </div>

    <!-- Content -->
    <div ref="scrollEl" class="flex-1 overflow-y-auto px-4 py-4 md:px-6 md:py-6 pb-24 scrollbar-thin">
      <!-- Status messages -->
      <div v-if="error" class="mb-6 bg-red-50 border border-red-200 rounded-xl p-4 flex items-center gap-3 text-red-700">
        <AlertCircle :size="20" class="flex-shrink-0" />
        <div>
          <div class="font-medium">加载失败</div>
          <div class="text-sm opacity-90">{{ error }}</div>
        </div>
      </div>
      
      <div v-if="status" class="mb-6 bg-green-50 border border-green-200 rounded-xl p-4 flex items-center gap-3 text-green-700 status-success shadow-sm">
        <div class="font-medium">{{ status }}</div>
      </div>
      
      <!-- Loading state -->
      <div v-if="loading && !playlists.length" class="h-64 flex items-center justify-center">
        <LoadingSpinner text="正在加载歌单..." />
      </div>
      
      <!-- Content sections -->
      <div v-else class="space-y-10 max-w-[1600px] mx-auto">
        <!-- High quality playlists -->
        <section v-if="highQualityPlaylists.length > 0" class="fade-in">
          <h2 class="text-xl font-bold text-gray-900 mb-5 flex items-center gap-2">
            <Star :size="24" class="text-yellow-500 fill-yellow-500" />
            精品歌单
          </h2>
          <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4 md:gap-6">
            <div
              v-for="playlist in highQualityPlaylists"
              :key="playlist.id"
              class="group relative flex flex-col gap-3 cursor-pointer"
              @click="goToPlaylist(playlist.id)"
            >
              <div class="relative aspect-square rounded-xl overflow-hidden shadow-sm transition-all duration-300 group-hover:shadow-xl group-hover:-translate-y-1">
                <button
                  class="absolute top-2 left-2 z-10 p-1.5 rounded-full backdrop-blur-md transition-colors"
                  :class="isLocalFavPlaylist(playlist.id) ? 'bg-pink-50 text-pink-600' : 'bg-black/40 text-white/90 hover:bg-pink-50 hover:text-pink-600'"
                  @click.stop="toggleLocalFavPlaylist({ id: playlist.id, source: 'qqmusic', name: playlist.name, coverImgUrl: playlist.coverImgUrl, playCount: playlist.playCount, creator: playlist.creator })"
                  :title="isLocalFavPlaylist(playlist.id) ? '取消本地收藏' : '本地收藏'"
                >
                  <Heart :size="14" :fill="isLocalFavPlaylist(playlist.id) ? 'currentColor' : 'none'" />
                </button>
                <img 
                  :src="playlist.coverImgUrl + '?param=300y300'" 
                  :alt="playlist.name"
                  class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                />
                <!-- Hover Overlay -->
                <div class="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center backdrop-blur-[2px]">
                   <div 
                    class="w-12 h-12 bg-white/90 rounded-full flex items-center justify-center text-blue-600 shadow-lg transform scale-50 group-hover:scale-100 transition-transform duration-300 hover:bg-white hover:scale-110"
                    @click.stop="addPlaylistToQueue(playlist)"
                    title="添加到播放队列"
                  >
                    <Play :size="24" fill="currentColor" class="ml-1" />
                  </div>
                </div>
                <!-- Play Count Badge -->
                <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-md text-white text-[10px] px-2 py-0.5 rounded-full flex items-center gap-1">
                  <Play :size="10" fill="currentColor" />
                  {{ formatPlayCount(playlist.playCount) }}
                </div>
              </div>
              
              <div class="min-w-0">
                <h3 class="font-bold text-gray-900 text-sm line-clamp-2 leading-snug group-hover:text-blue-600 transition-colors mb-1" :title="playlist.name">
                  {{ playlist.name }}
                </h3>
                <p class="text-xs text-gray-500 flex items-center gap-1 truncate">
                  <User :size="12" />
                  {{ playlist.creator?.nickname }}
                </p>
              </div>
            </div>
          </div>
        </section>

        <!-- Recommended playlists -->
        <section v-if="recommendPlaylists.length > 0" class="fade-in">
          <h2 class="text-xl font-bold text-gray-900 mb-5 flex items-center gap-2">
            <TrendingUp :size="24" class="text-green-500" />
            推荐歌单
          </h2>
          <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4 md:gap-6">
            <div
              v-for="playlist in recommendPlaylists"
              :key="playlist.id"
              class="group relative flex flex-col gap-3 cursor-pointer"
              @click="goToPlaylist(playlist.id)"
            >
              <div class="relative aspect-square rounded-xl overflow-hidden shadow-sm transition-all duration-300 group-hover:shadow-xl group-hover:-translate-y-1">
                <button
                  class="absolute top-2 left-2 z-10 p-1.5 rounded-full backdrop-blur-md transition-colors"
                  :class="isLocalFavPlaylist(playlist.id) ? 'bg-pink-50 text-pink-600' : 'bg-black/40 text-white/90 hover:bg-pink-50 hover:text-pink-600'"
                  @click.stop="toggleLocalFavPlaylist({ id: playlist.id, source: 'qqmusic', name: playlist.name, picUrl: playlist.picUrl, playCount: playlist.playCount, creator: playlist.creator })"
                  :title="isLocalFavPlaylist(playlist.id) ? '取消本地收藏' : '本地收藏'"
                >
                  <Heart :size="14" :fill="isLocalFavPlaylist(playlist.id) ? 'currentColor' : 'none'" />
                </button>
                <img 
                  :src="playlist.picUrl + '?param=300y300'" 
                  :alt="playlist.name"
                  class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                />
                 <!-- Hover Overlay -->
                <div class="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center backdrop-blur-[2px]">
                   <div 
                    class="w-12 h-12 bg-white/90 rounded-full flex items-center justify-center text-green-600 shadow-lg transform scale-50 group-hover:scale-100 transition-transform duration-300 hover:bg-white hover:scale-110"
                    @click.stop="addPlaylistToQueue(playlist)"
                    title="添加到播放队列"
                  >
                    <Play :size="24" fill="currentColor" class="ml-1" />
                  </div>
                </div>
                <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-md text-white text-[10px] px-2 py-0.5 rounded-full flex items-center gap-1">
                  <Play :size="10" fill="currentColor" />
                  {{ formatPlayCount(playlist.playCount) }}
                </div>
              </div>
              <div class="min-w-0">
                <h3 class="font-bold text-gray-900 text-sm line-clamp-2 leading-snug group-hover:text-green-600 transition-colors mb-1" :title="playlist.name">
                  {{ playlist.name }}
                </h3>
              </div>
            </div>
          </div>
        </section>

        <!-- All playlists -->
        <section v-if="playlists.length > 0" class="fade-in">
          <h2 class="text-xl font-bold text-gray-900 mb-5 flex items-center gap-2">
            <ListMusic :size="24" class="text-blue-500" />
            QQ 音乐 · {{ selectedCategory }} 歌单
          </h2>
          <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4 md:gap-6">
            <div
              v-for="playlist in playlists"
              :key="playlist.id"
              class="group relative flex flex-col gap-3 cursor-pointer"
              @click="goToPlaylist(playlist.id)"
            >
              <div class="relative aspect-square rounded-xl overflow-hidden shadow-sm transition-all duration-300 group-hover:shadow-xl group-hover:-translate-y-1">
                <button
                  class="absolute top-2 left-2 z-10 p-1.5 rounded-full backdrop-blur-md transition-colors"
                  :class="isLocalFavPlaylist(playlist.id) ? 'bg-pink-50 text-pink-600' : 'bg-black/40 text-white/90 hover:bg-pink-50 hover:text-pink-600'"
                  @click.stop="toggleLocalFavPlaylist({ id: playlist.id, source: 'qqmusic', name: playlist.name, coverImgUrl: playlist.coverImgUrl, playCount: playlist.playCount, creator: playlist.creator })"
                  :title="isLocalFavPlaylist(playlist.id) ? '取消本地收藏' : '本地收藏'"
                >
                  <Heart :size="14" :fill="isLocalFavPlaylist(playlist.id) ? 'currentColor' : 'none'" />
                </button>
                <img 
                  :src="playlist.coverImgUrl + '?param=300y300'" 
                  :alt="playlist.name"
                  class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                />
                 <!-- Hover Overlay -->
                <div class="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center backdrop-blur-[2px]">
                   <div 
                    class="w-12 h-12 bg-white/90 rounded-full flex items-center justify-center text-blue-600 shadow-lg transform scale-50 group-hover:scale-100 transition-transform duration-300 hover:bg-white hover:scale-110"
                    @click.stop="addPlaylistToQueue(playlist)"
                    title="添加到播放队列"
                  >
                    <Play :size="24" fill="currentColor" class="ml-1" />
                  </div>
                </div>
                <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-md text-white text-[10px] px-2 py-0.5 rounded-full flex items-center gap-1">
                  <Play :size="10" fill="currentColor" />
                  {{ formatPlayCount(playlist.playCount) }}
                </div>
              </div>
              
              <div class="min-w-0">
                <h3 class="font-bold text-gray-900 text-sm line-clamp-2 leading-snug group-hover:text-blue-600 transition-colors mb-1" :title="playlist.name">
                  {{ playlist.name }}
                </h3>
                <p class="text-xs text-gray-500 flex items-center gap-1 truncate">
                  <User :size="12" />
                  {{ playlist.creator?.nickname }}
                </p>
              </div>
            </div>
          </div>
        </section>

        <!-- Empty state -->
        <EmptyState
          v-if="!loading && playlists.length === 0 && highQualityPlaylists.length === 0 && recommendPlaylists.length === 0"
          :icon="ListMusic"
          title="暂无歌单"
          description="尝试更换关键词或刷新页面"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  line-clamp: 2;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
