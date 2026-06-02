import axios from 'axios'

type ErrorPayload = {
  detail?: unknown
  message?: unknown
  error?: unknown
}

function normalizeDetail(detail: unknown): string | null {
  if (!detail) return null
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const text = detail
      .map((item) => normalizeDetail(item))
      .filter(Boolean)
      .join('；')
    return text || null
  }
  if (typeof detail === 'object') {
    const objectDetail = detail as Record<string, unknown>
    if (typeof objectDetail.msg === 'string') return objectDetail.msg
    if (typeof objectDetail.message === 'string') return objectDetail.message
    return JSON.stringify(objectDetail)
  }
  return String(detail)
}

export function getErrorMessage(error: unknown, fallback = '请求失败，请稍后再试'): string {
  if (axios.isAxiosError(error)) {
    const payload = error.response?.data as ErrorPayload | undefined
    return (
      normalizeDetail(payload?.detail) ||
      normalizeDetail(payload?.message) ||
      normalizeDetail(payload?.error) ||
      error.message ||
      fallback
    )
  }
  if (error instanceof Error) return error.message || fallback
  if (typeof error === 'string') return error
  return fallback
}
