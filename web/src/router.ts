import { createRouter, createWebHistory, type RouteLocationNormalized } from 'vue-router'
import SearchView from './views/SearchView.vue'
import LikesView from './views/LikesView.vue'
import FavoritesView from './views/FavoritesView.vue'
import PlaylistsView from './views/PlaylistsView.vue'
import PlaylistDetailView from './views/PlaylistDetailView.vue'
import QueueView from './views/QueueView.vue'
import HistoryView from './views/HistoryView.vue'
import LyricsView from './views/LyricsView.vue'
import SettingsView from './views/SettingsView.vue'
import LoginView from './views/LoginView.vue'
import ChangePasswordView from './views/ChangePasswordView.vue'
import { refreshAuth } from './auth'
import { appConfig } from './appConfig'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/search' },
    { path: '/search', component: SearchView },
    { path: '/likes', component: LikesView, meta: { neteaseOnly: true } },
    { path: '/favorites', component: FavoritesView },
    { path: '/playlists', component: PlaylistsView, meta: { neteaseOnly: true } },
    { path: '/playlist/:id', component: PlaylistDetailView, meta: { neteaseOnly: true } },
    { path: '/queue', component: QueueView },
    { path: '/history', component: HistoryView },
    { path: '/login', name: 'login', component: LoginView, meta: { authPage: true } },
    { path: '/change-password', name: 'change-password', component: ChangePasswordView, meta: { authPage: true, requiresAuth: true } },
    { path: '/settings', component: SettingsView, meta: { requiresAuth: true } },
    { path: '/cookie', redirect: { path: '/settings', query: { group: 'authorization' } } },
    { path: '/lyrics', component: LyricsView },
  ],
})

router.beforeEach(async (to: RouteLocationNormalized) => {
  if (to.meta.neteaseOnly && !appConfig.neteaseEnabled) {
    return '/search'
  }
  const status = await refreshAuth(true)
  if (status.authenticated && status.must_change_password && to.name !== 'change-password') {
    return { name: 'change-password' }
  }
  if (to.meta.requiresAuth && !status.authenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && status.authenticated) {
    return status.must_change_password ? { name: 'change-password' } : '/settings'
  }
  return true
})
