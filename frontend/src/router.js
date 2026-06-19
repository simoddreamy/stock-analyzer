import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/stocks' },
  { path: '/stocks', component: () => import('./views/StocksView.vue') },
  { path: '/explore', component: () => import('./views/ExploreView.vue') },
  { path: '/settings', component: () => import('./views/SettingsView.vue') },
]

export default createRouter({
  history: createWebHistory(),
  routes
})