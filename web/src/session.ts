let csrfToken = ''

export function getCsrfToken(): string {
  return csrfToken
}

export function setCsrfToken(value: string): void {
  csrfToken = value || ''
}
