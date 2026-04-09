type NeteaseArtist = { name: string }

type NeteaseAlbum = {
  name?: string
  picUrl?: string
}

export type FavoriteSong = {
  id: number
  name: string
  source?: string
  track_id?: string
  video_id?: string
  song_mid?: string
  album_mid?: string
  artist?: string
  album?: string
  artwork_url?: string
  webpage_url?: string
  description?: string
  ar?: NeteaseArtist[]
  al?: NeteaseAlbum
  dt?: number
  _fav_at?: number
}

export type FavoritePlaylist = {
  id: number
  name: string
  coverImgUrl?: string
  picUrl?: string
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
    const obj = JSON.parse(raw)
    return (obj as T) ?? fallback
  } catch {
    return fallback
  }
}

function normalizeBilibiliVideoId(value: any): string {
  const raw = String(value ?? '').trim()
  if (!raw) return ''
  const match = raw.match(BILIBILI_VIDEO_ID_RE)
  if (!match) return ''
  const token = match[1]
  if (token.toLowerCase().startsWith('bv')) {
    return `BV${token.slice(2)}`
  }
  return token.toLowerCase()
}

function normalizeProtocolUrl(value: any): string {
  const raw = String(value ?? '').trim()
  if (!raw) return ''
  if (raw.startsWith('//')) return `https:${raw}`
  return raw
}

function parseDurationMs(value: any): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
    return value > 1000 ? value : value * 1000
  }

  const raw = String(value ?? '').replace(/,/g, '').trim()
  if (!raw) return undefined

  if (/^\d+$/.test(raw)) {
    const numeric = Number(raw)
    if (!Number.isFinite(numeric) || numeric <= 0) return undefined
    return numeric > 1000 ? numeric : numeric * 1000
  }

  const parts = raw.split(':').map((part) => Number(part))
  if (!parts.length || parts.some((part) => !Number.isFinite(part) || part < 0)) {
    return undefined
  }

  let seconds = 0
  for (const part of parts) {
    seconds = seconds * 60 + part
  }
  return seconds > 0 ? seconds * 1000 : undefined
}

function hashToPositiveInt(value: string): number {
  let hash = 2166136261
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  const normalized = hash >>> 0
  return normalized > 0 ? normalized : 1
}

function inferSongSource(input: any): string {
  const explicit = String(input?.source ?? '').trim().toLowerCase()
  if (explicit) return explicit

  const trackId = String(input?.track_id ?? '').trim().toLowerCase()
  if (trackId.startsWith('bilibili:')) return 'bilibili'
  if (trackId.startsWith('qqmusic:')) return 'qqmusic'
  if (trackId.startsWith('netease:')) return 'netease'

  if (normalizeBilibiliVideoId(input?.video_id || input?.bvid || input?.webpage_url || input?.arcurl || input?.track_id)) {
    return 'bilibili'
  }

  if (String(input?.song_mid || input?.songmid || input?.mid || '').trim()) {
    return 'qqmusic'
  }

  return 'netease'
}

function buildFavoriteSongKey(input: any, source = inferSongSource(input)): string {
  if (source === 'bilibili') {
    const videoId = normalizeBilibiliVideoId(
      input?.video_id || input?.bvid || input?.track_id || input?.webpage_url || input?.arcurl,
    )
    if (videoId) return `bilibili:${videoId}`
  }

  if (source === 'qqmusic') {
    const songMid = String(input?.song_mid || input?.songmid || input?.mid || '').trim()
    if (songMid) return `qqmusic:${songMid}`
  }

  if (typeof input === 'string') {
    const raw = input.trim()
    if (raw.includes(':')) return raw
  }

  const trackId = String(input?.track_id || '').trim()
  if (trackId) return trackId

  const id = Number(input?.id ?? input)
  if (Number.isFinite(id) && id > 0) {
    return `${source || 'netease'}:${id}`
  }

  return ''
}

function extractNumericTrackId(trackKey: string, prefix: string): number | null {
  const normalized = String(trackKey || '').trim()
  if (!normalized.startsWith(`${prefix}:`)) return null
  const raw = normalized.slice(prefix.length + 1).trim()
  const parsed = Number(raw)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

function getSongArtistName(input: any, source: string): string {
  if (source === 'bilibili') {
    return String(input?.artist || input?.author || input?.owner?.name || '').trim()
  }

  if (source === 'qqmusic') {
    const names = ((input?.singer || input?.artists) || [])
      .map((artist: any) => String(artist?.name || '').trim())
      .filter(Boolean)
    return names.join(', ')
  }

  const names = ((input?.ar || input?.artists) || [])
    .map((artist: any) => String(artist?.name || '').trim())
    .filter(Boolean)
  const joined = names.join(', ')
  return joined || String(input?.artist || '').trim()
}

function getSongAlbumName(input: any, source: string): string {
  if (source === 'bilibili') {
    return String(input?.album || input?.typename || '').trim()
  }

  if (source === 'qqmusic') {
    return String(input?.album?.name || input?.albumname || '').trim()
  }

  return String(input?.al?.name || input?.album?.name || input?.album || '').trim()
}

function getSongArtworkUrl(input: any, source: string): string {
  if (source === 'bilibili') {
    return normalizeProtocolUrl(input?.artwork_url || input?.artwork || input?.pic || input?.thumbnail || input?.cover_url)
  }

  if (source === 'qqmusic') {
    const explicit = normalizeProtocolUrl(input?.artwork_url || input?.artwork || input?.cover_url)
    if (explicit) return explicit
    const albumMid = String(input?.album?.pmid || input?.album?.mid || input?.albummid || '').trim()
    return albumMid ? `https://y.gtimg.cn/music/photo_new/T002R300x300M000${albumMid}.jpg` : ''
  }

  const raw = normalizeProtocolUrl(
    input?.artwork_url || input?.artwork || input?.cover_url || input?.al?.picUrl || input?.album?.picUrl || input?.artists?.[0]?.img1v1Url,
  )
  return raw ? raw.replace(/\?param=\d+y\d+$/, '') : ''
}

function getSongWebpageUrl(input: any, source: string): string {
  if (source !== 'bilibili') return ''
  const explicit = normalizeProtocolUrl(input?.webpage_url || input?.arcurl || input?.url)
  if (explicit) return explicit

  const videoId = normalizeBilibiliVideoId(input?.video_id || input?.bvid || input?.track_id)
  return videoId ? `https://www.bilibili.com/video/${videoId}` : ''
}

function normalizeArtistList(input: any, artistName: string): NeteaseArtist[] | undefined {
  const arRaw = input?.ar || input?.artists || input?.singer
  const normalized = Array.isArray(arRaw)
    ? arRaw
        .map((artist: any) => ({ name: String(artist?.name || '').trim() }))
        .filter((artist: NeteaseArtist) => artist.name)
    : []

  if (normalized.length > 0) return normalized
  if (!artistName) return undefined
  return [{ name: artistName }]
}

function normalizeAlbum(input: any, albumName: string, artworkUrl: string): NeteaseAlbum | undefined {
  const alRaw = input?.al
  if (alRaw && typeof alRaw === 'object') {
    return {
      name: alRaw?.name ? String(alRaw.name).trim() : (albumName || undefined),
      picUrl: alRaw?.picUrl ? normalizeProtocolUrl(alRaw.picUrl) : (artworkUrl || undefined),
    }
  }

  const albumRaw = input?.album
  if (albumRaw && typeof albumRaw === 'object') {
    return {
      name: albumRaw?.name ? String(albumRaw.name).trim() : (albumName || undefined),
      picUrl: albumRaw?.picUrl
        ? normalizeProtocolUrl(albumRaw.picUrl)
        : albumRaw?.pic_url
          ? normalizeProtocolUrl(albumRaw.pic_url)
          : (artworkUrl || undefined),
    }
  }

  if (!albumName && !artworkUrl) return undefined
  return {
    name: albumName || undefined,
    picUrl: artworkUrl || undefined,
  }
}

function normalizeSong(input: any): FavoriteSong | null {
  const source = inferSongSource(input)
  const trackKey = buildFavoriteSongKey(input, source)

  const derivedNeteaseId = extractNumericTrackId(trackKey, 'netease')
  const idValue = Number(input?.id)
  const id = derivedNeteaseId
    ?? (Number.isFinite(idValue) && idValue > 0 ? idValue : (trackKey ? hashToPositiveInt(trackKey) : NaN))
  if (!Number.isFinite(id) || id <= 0) return null

  const name = String(input?.name || input?.title || '').trim()
  if (!name) return null

  const artist = getSongArtistName(input, source)
  const album = getSongAlbumName(input, source)
  const artworkUrl = getSongArtworkUrl(input, source)
  const dt = parseDurationMs(input?.dt ?? input?.duration_ms ?? input?.duration)
  const videoId = normalizeBilibiliVideoId(input?.video_id || input?.bvid || input?.track_id || input?.webpage_url || input?.arcurl)
  const songMid = String(input?.song_mid || input?.songmid || input?.mid || '').trim()
  const albumMid = String(input?.album_mid || input?.album?.mid || input?.albummid || '').trim()
  const description = String(input?.description || input?.desc || '').trim()
  const webpageUrl = getSongWebpageUrl(input, source)

  return {
    id,
    name,
    source,
    track_id: trackKey || (input?.track_id ? String(input.track_id).trim() : undefined),
    video_id: videoId || undefined,
    song_mid: songMid || undefined,
    album_mid: albumMid || undefined,
    artist: artist || undefined,
    album: album || undefined,
    artwork_url: artworkUrl || undefined,
    webpage_url: webpageUrl || undefined,
    description: description || undefined,
    ar: normalizeArtistList(input, artist),
    al: normalizeAlbum(input, album, artworkUrl),
    dt,
  }
}

function normalizePlaylist(input: any): FavoritePlaylist | null {
  const id = Number(input?.id)
  if (!Number.isFinite(id) || id <= 0) return null

  const name = String(input?.name || '').trim()
  if (!name) return null

  const coverImgUrl = input?.coverImgUrl ? String(input.coverImgUrl) : undefined
  const picUrl = input?.picUrl ? String(input.picUrl) : undefined
  const playCount = Number(input?.playCount)

  const creator = input?.creator && typeof input.creator === 'object'
    ? { nickname: input.creator.nickname ? String(input.creator.nickname) : undefined }
    : undefined

  return {
    id,
    name,
    coverImgUrl,
    picUrl,
    playCount: Number.isFinite(playCount) ? playCount : undefined,
    creator,
  }
}

function isSameFavoriteSong(a: any, b: any): boolean {
  const keyA = buildFavoriteSongKey(a)
  const keyB = buildFavoriteSongKey(b)
  if (keyA && keyB) return keyA === keyB

  const idA = Number(a?.id ?? a)
  const idB = Number(b?.id ?? b)
  return Number.isFinite(idA) && idA > 0 && idA === idB
}

export function getFavoriteSongKey(songLike: any): string {
  return buildFavoriteSongKey(songLike)
}

export function getFavoriteSongs(): FavoriteSong[] {
  const raw = localStorage.getItem(SONGS_KEY)
  const arr = safeParseJson<any[]>(raw, [])
  if (!Array.isArray(arr)) return []

  return arr
    .map((item) => {
      const normalized = normalizeSong(item)
      if (!normalized) return null
      const favAt = Number(item?._fav_at)
      return {
        ...normalized,
        _fav_at: Number.isFinite(favAt) && favAt > 0 ? favAt : undefined,
      }
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
  const idx = list.findIndex((item) => isSameFavoriteSong(item, song))

  if (idx >= 0) {
    list.splice(idx, 1)
    localStorage.setItem(SONGS_KEY, JSON.stringify(list))
    return false
  }

  const now = Date.now()
  const next: FavoriteSong = { ...song, _fav_at: now }
  const out = [next, ...list]
  localStorage.setItem(SONGS_KEY, JSON.stringify(out))
  return true
}

export function removeFavoriteSong(songLike: any): void {
  const list = getFavoriteSongs().filter((song) => !isSameFavoriteSong(song, songLike))
  localStorage.setItem(SONGS_KEY, JSON.stringify(list))
}

export function getFavoritePlaylists(): FavoritePlaylist[] {
  const raw = localStorage.getItem(PLAYLISTS_KEY)
  const arr = safeParseJson<any[]>(raw, [])
  if (!Array.isArray(arr)) return []
  return arr.filter(Boolean)
}

export function isFavoritePlaylist(playlistId: number | string): boolean {
  const id = Number(playlistId)
  if (!Number.isFinite(id) || id <= 0) return false
  return getFavoritePlaylists().some((playlist) => Number(playlist?.id) === id)
}

export function toggleFavoritePlaylist(playlistLike: any): boolean {
  const playlist = normalizePlaylist(playlistLike)
  if (!playlist) return false

  const list = getFavoritePlaylists()
  const idx = list.findIndex((item) => Number(item?.id) === playlist.id)

  if (idx >= 0) {
    list.splice(idx, 1)
    localStorage.setItem(PLAYLISTS_KEY, JSON.stringify(list))
    return false
  }

  const now = Date.now()
  const next: FavoritePlaylist = { ...playlist, _fav_at: now }
  const out = [next, ...list]
  localStorage.setItem(PLAYLISTS_KEY, JSON.stringify(out))
  return true
}

export function removeFavoritePlaylist(playlistId: number | string): void {
  const id = Number(playlistId)
  if (!Number.isFinite(id) || id <= 0) return
  const list = getFavoritePlaylists().filter((playlist) => Number(playlist?.id) !== id)
  localStorage.setItem(PLAYLISTS_KEY, JSON.stringify(list))
}
