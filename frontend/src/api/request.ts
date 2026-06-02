
import axios from "axios"

const rawApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() || ''
export const API_BASE_URL = rawApiBaseUrl.replace(/\/+$/, '')

function getApiOrigin() {
    if (API_BASE_URL) return API_BASE_URL
    if (typeof window !== 'undefined' && window.location?.origin) {
        return window.location.origin
    }
    return ''
}

export function buildApiUrl(path: string) {
    if (/^https?:\/\//i.test(path)) return path
    const normalizedPath = path.startsWith('/') ? path : `/${path}`
    return `${getApiOrigin()}${normalizedPath}`
}


const api = axios.create({
    baseURL: API_BASE_URL || '/',
    timeout: 180000,
    withCredentials: true,
})
export default api
