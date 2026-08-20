export type MusicSource = 'qqmusic' | 'bilibili'

type Artist = { name: string }

export type FavoriteSong = {
  id: number
  name: string
  source: MusicSource
  track_id: string
  video_id?: string
  song_mid?: string
  album_mid?: string
  artist?: string
  album?: string
  artwork_url?: string
  webpage_url?: string
  description?: string
  artists?: Artist[]
  duration_ms?: number
  _fav_at?: number
}

export type FavoritePlaylist = {
  id: number
  name: string
  source: 'qqmusic'
  coverImgUrl?: string
  playCount?: number
  creator?: { nickname?: string }
  _fav_at?: number
}

const SONGS_KEY = 'tsbot:fav:songs'
const PLAYLISTS_KEY = 'tsbot:fav:playlists'
const BILIBILI_VIDEO_ID_RE = /(BV[0-9A-Za-z]+|av\d+)/i

function safeParseJson<T>(raw: string | null, fallback: T): T {
  if (!raw) return fallback
  try {
    return (JSON.parse(raw) as T) ?? fallback
  } catch {
    return fallback
  }
}

function normalizeBilibiliVideoId(value: unknown): string {
  const raw = String(value ?? '').trim()
  const match = raw.match(BILIBILI_VIDEO_ID_RE)
  if (!match) return ''
  const token = match[1]
  return token.toLowerCase().startsWith('bv') ? `BV${token.slice(2)}` : token.toLowerCase()
}

function normalizeProtocolUrl(value: unknown): string {
  const raw = String(value ?? '').trim()
  if (!raw) return ''
  return raw.startsWith('//') ? `https:${raw}` : raw
}

function parseDurationMs(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
    return value > 1000 ? value : value * 1000
  }

  const raw = String(value ?? '').replace(/,/g, '').trim()
  if (!raw) return undefined
  if (/^\d+$/.test(raw)) {
    const numeric = Number(raw)
    return Number.isFinite(numeric) && numeric > 0 ? (numeric > 1000 ? numeric : numeric * 1000) : undefined
  }

  const parts = raw.split(':').map(Number)
  if (!parts.length || parts.some((part) => !Number.isFinite(part) || part < 0)) return undefined
  const seconds = parts.reduce((total, part) => total * 60 + part, 0)
  return seconds > 0 ? seconds * 1000 : undefined
}

function hashToPositiveInt(value: string): number {
  let hash = 2166136261
  for (let index = 0; index < value.length; index++) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0) || 1
}

function isMusicSource(value: unknown): value is MusicSource {
  return value === 'qqmusic' || value === 'bilibili'
}

function inferSongSource(input: any): MusicSource | null {
  const explicit = String(input?.source ?? '').trim().toLowerCase()
  if (isMusicSource(explicit)) return explicit

  const trackId = String(input?.track_id ?? '').trim().toLowerCase()
  if (trackId.startsWith('qqmusic:')) return 'qqmusic'
  if (trackId.startsWith('bilibili:')) return 'bilibili'

  if (normalizeBilibiliVideoId(input?.video_id || input?.bvid || input?.webpage_url || input?.arcurl || input?.track_id)) {
    return 'bilibili'
  }
  if (String(input?.song_mid || input?.songmid || input?.mid || '').trim()) return 'qqmusic'
  return null
}

function getSongKey(input: any, source: MusicSource): string {
  if (source === 'bilibili') {
    const videoId = normalizeBilibiliVideoId(
      input?.video_id || input?.bvid || input?.track_id || input?.webpage_url || input?.arcurl,
    )
    return videoId ? `bilibili:${videoId}` : ''
  }

  const songMid = String(input?.song_mid || input?.songmid || input?.mid || '').trim()
  if (songMid) return `qqmusic:${songMid}`
  const trackId = String(input?.track_id || '').trim()
  return trackId.startsWith('qqmusic:') ? trackId : ''
}

function getArtist(input: any, source: MusicSource): string {
  if (source === 'bilibili') {
    return String(input?.artist || input?.author || input?.owner?.name || '').trim()
  }

  const artist = input?.artist
  if (typeof artist === 'string' && artist.trim()) return artist.trim()
  const candidates = input?.singer || input?.artists
  if (!Array.isArray(candidates)) return ''
  return candidates.map((item: any) => String(item?.name || item || '').trim()).filter(Boolean).join(', ')
}

function getAlbum(input: any, source: MusicSource): string {
  if (source === 'bilibili') return String(input?.album || input?.typename || '').trim()
  return String(input?.album?.name || input?.album?.title || input?.albumname || input?.album || '').trim()
}

function getArtwork(input: any, source: MusicSource): string {
  const explicit = normalizeProtocolUrl(input?.artwork_url || input?.artwork || input?.cover_url)
  if (explicit) return explicit
  if (source === 'bilibili') return normalizeProtocolUrl(input?.pic || input?.thumbnail)

  const albumMid = String(input?.album?.pmid || input?.album?.mid || input?.albummid || input?.album_mid || '').trim()
  return albumMid ? `https://y.gtimg.cn/music/photo_new/T002R300x300M000${albumMid}.jpg` : ''
}

function getWebpageUrl(input: any, source: MusicSource): string {
  if (source !== 'bilibili') return ''
  const explicit = normalizeProtocolUrl(input?.webpage_url || input?.arcurl || input?.url)
  if (explicit) return explicit
  const videoId = normalizeBilibiliVideoId(input?.video_id || input?.bvid || input?.track_id)
  return videoId ? `https://www.bilibili.com/video/${videoId}` : ''
}

function normalizeSong(input: any): FavoriteSong | null {
  const source = inferSongSource(input)
  if (!source) return null

  const trackId = getSongKey(input, source)
  const name = String(input?.name || input?.songname || input?.title || '').trim()
  if (!trackId || !name) return null

  const artist = getArtist(input, source)
  const album = getAlbum(input, source)
  const artworkUrl = getArtwork(input, source)
  const videoId = normalizeBilibiliVideoId(input?.video_id || input?.bvid || input?.track_id || input?.webpage_url || input?.arcurl)
  const songMid = String(input?.song_mid || input?.songmid || input?.mid || '').trim()
  const albumMid = String(input?.album_mid || input?.album?.mid || input?.albummid || '').trim()

  return {
    id: hashToPositiveInt(trackId),
    name,
    source,
    track_id: trackId,
    video_id: videoId || undefined,
    song_mid: songMid || undefined,
    album_mid: albumMid || undefined,
    artist: artist || undefined,
    album: album || undefined,
    artwork_url: artworkUrl || undefined,
    webpage_url: getWebpageUrl(input, source) || undefined,
    description: String(input?.description || input?.desc || '').trim() || undefined,
    artists: artist ? [{ name: artist }] : undefined,
    duration_ms: parseDurationMs(input?.duration_ms ?? input?.duration ?? input?.interval),
  }
}

function normalizePlaylist(input: any): FavoritePlaylist | null {
  if (String(input?.source || '').trim().toLowerCase() !== 'qqmusic') return null
  const id = Number(input?.id)
  const name = String(input?.name || '').trim()
  if (!Number.isFinite(id) || id <= 0 || !name) return null

  const coverImgUrl = normalizeProtocolUrl(input?.coverImgUrl || input?.cover_url || input?.picUrl)
  const playCount = Number(input?.playCount ?? input?.play_count)
  const creator = String(input?.creator?.nickname || input?.creator || '').trim()
  return {
    id,
    name,
    source: 'qqmusic',
    coverImgUrl: coverImgUrl || undefined,
    playCount: Number.isFinite(playCount) ? playCount : undefined,
    creator: creator ? { nickname: creator } : undefined,
  }
}

function isSameFavoriteSong(a: any, b: any): boolean {
  const sourceA = inferSongSource(a)
  const sourceB = inferSongSource(b)
  if (!sourceA || !sourceB || sourceA !== sourceB) return false
  const keyA = getSongKey(a, sourceA)
  const keyB = getSongKey(b, sourceB)
  return Boolean(keyA && keyB && keyA === keyB)
}

export function getFavoriteSongKey(songLike: any): string {
  const source = inferSongSource(songLike)
  return source ? getSongKey(songLike, source) : ''
}

export function getFavoriteSongs(): FavoriteSong[] {
  const raw = safeParseJson<any[]>(localStorage.getItem(SONGS_KEY), [])
  if (!Array.isArray(raw)) return []
  return raw
    .map((item) => {
      const song = normalizeSong(item)
      if (!song) return null
      const favAt = Number(item?._fav_at)
      const favorite: FavoriteSong = { ...song }
      if (Number.isFinite(favAt) && favAt > 0) favorite._fav_at = favAt
      return favorite
    })
    .filter((item): item is FavoriteSong => Boolean(item))
}

export function isFavoriteSong(songLike: any): boolean {
  return getFavoriteSongs().some((song) => isSameFavoriteSong(song, songLike))
}

export function toggleFavoriteSong(songLike: any): boolean {
  const song = normalizeSong(songLike)
  if (!song) return false
  const list = getFavoriteSongs()
  const index = list.findIndex((item) => isSameFavoriteSong(item, song))
  if (index >= 0) {
    list.splice(index, 1)
    localStorage.setItem(SONGS_KEY, JSON.stringify(list))
    return false
  }

  const next = { ...song, _fav_at: Date.now() }
  localStorage.setItem(SONGS_KEY, JSON.stringify([next, ...list]))
  return true
}

export function removeFavoriteSong(songLike: any): void {
  const list = getFavoriteSongs().filter((song) => !isSameFavoriteSong(song, songLike))
  localStorage.setItem(SONGS_KEY, JSON.stringify(list))
}

export function getFavoritePlaylists(): FavoritePlaylist[] {
  const raw = safeParseJson<any[]>(localStorage.getItem(PLAYLISTS_KEY), [])
  if (!Array.isArray(raw)) return []
  return raw
    .map((item) => {
      const playlist = normalizePlaylist(item)
      if (!playlist) return null
      const favAt = Number(item?._fav_at)
      const favorite: FavoritePlaylist = { ...playlist }
      if (Number.isFinite(favAt) && favAt > 0) favorite._fav_at = favAt
      return favorite
    })
    .filter((item): item is FavoritePlaylist => Boolean(item))
}

export function isFavoritePlaylist(playlistId: number | string): boolean {
  const id = Number(playlistId)
  return Number.isFinite(id) && id > 0 && getFavoritePlaylists().some((playlist) => playlist.id === id)
}

export function toggleFavoritePlaylist(playlistLike: any): boolean {
  const playlist = normalizePlaylist(playlistLike)
  if (!playlist) return false
  const list = getFavoritePlaylists()
  const index = list.findIndex((item) => item.id === playlist.id)
  if (index >= 0) {
    list.splice(index, 1)
    localStorage.setItem(PLAYLISTS_KEY, JSON.stringify(list))
    return false
  }

  const next = { ...playlist, _fav_at: Date.now() }
  localStorage.setItem(PLAYLISTS_KEY, JSON.stringify([next, ...list]))
  return true
}

export function removeFavoritePlaylist(playlistId: number | string): void {
  const id = Number(playlistId)
  if (!Number.isFinite(id) || id <= 0) return
  localStorage.setItem(PLAYLISTS_KEY, JSON.stringify(getFavoritePlaylists().filter((playlist) => playlist.id !== id)))
}
