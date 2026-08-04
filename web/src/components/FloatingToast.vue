<script setup lang="ts">
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-vue-next'

withDefaults(defineProps<{
  message: string
  type?: 'success' | 'error' | 'info'
  title?: string
}>(), {
  type: 'info',
  title: '',
})

defineEmits<{
  close: []
}>()
</script>

<template>
  <Teleport to="body">
    <transition name="toast-fade">
      <div
        v-if="message"
        class="pointer-events-none fixed inset-x-4 bottom-24 z-[90] flex justify-center sm:inset-x-auto sm:right-6 sm:justify-end"
      >
        <div :class="['theme-floating-panel pointer-events-auto w-full max-w-sm rounded-lg border bg-white/95 px-4 py-3 shadow-2xl backdrop-blur-xl', `theme-toast-${type}`]" role="status" aria-live="polite">
          <div class="flex items-start gap-3">
            <CheckCircle2 v-if="type === 'success'" :size="19" class="mt-0.5 shrink-0 text-green-600" />
            <AlertCircle v-else-if="type === 'error'" :size="19" class="mt-0.5 shrink-0 text-red-600" />
            <Info v-else :size="19" class="mt-0.5 shrink-0 text-blue-600" />
            <div class="min-w-0 flex-1">
              <div v-if="title" class="text-sm font-semibold text-gray-900">{{ title }}</div>
              <div :class="['break-words text-sm', title ? 'mt-0.5 text-gray-600' : 'font-medium text-gray-800']">{{ message }}</div>
            </div>
            <button type="button" class="-mr-1 -mt-1 p-1 text-gray-400 hover:text-gray-700" title="关闭" @click="$emit('close')">
              <X :size="16" />
            </button>
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<style scoped>
.toast-fade-enter-active,
.toast-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.toast-fade-enter-from,
.toast-fade-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>
