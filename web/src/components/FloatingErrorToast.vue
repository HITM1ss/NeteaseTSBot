<script setup lang="ts">
import { AlertCircle } from 'lucide-vue-next'

defineProps<{
  message: string
}>()
</script>

<template>
  <Teleport to="body">
    <transition name="toast-fade">
      <div
        v-if="message"
        class="pointer-events-none fixed inset-x-4 bottom-24 z-[90] flex justify-center sm:inset-x-auto sm:right-6 sm:justify-end"
      >
        <div class="theme-floating-panel w-full max-w-md rounded-2xl border border-red-200 bg-white/95 px-4 py-3 shadow-2xl backdrop-blur-xl">
          <div class="flex items-start gap-3 text-red-700">
            <AlertCircle :size="18" class="mt-0.5 shrink-0" />
            <div class="min-w-0">
              <div class="font-medium">操作失败</div>
              <div class="mt-0.5 break-words text-sm text-red-600">{{ message }}</div>
            </div>
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
