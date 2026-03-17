import { onUnmounted, ref } from 'vue'

export function useTransientMessage(duration = 3000) {
  const message = ref('')
  let timer: number | null = null

  function clearMessage() {
    if (timer !== null) {
      window.clearTimeout(timer)
      timer = null
    }
    message.value = ''
  }

  function showMessage(nextMessage: string) {
    if (!nextMessage) {
      clearMessage()
      return
    }

    message.value = nextMessage

    if (timer !== null) {
      window.clearTimeout(timer)
    }

    timer = window.setTimeout(() => {
      message.value = ''
      timer = null
    }, duration)
  }

  onUnmounted(() => {
    if (timer !== null) {
      window.clearTimeout(timer)
    }
  })

  return {
    message,
    showMessage,
    clearMessage,
  }
}
