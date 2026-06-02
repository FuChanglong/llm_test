import { useEffect, useState } from 'react'

export type AppearanceMode = 'system' | 'light' | 'focus'
export type InterfaceLanguage = 'zh-CN' | 'en-US'
export type SendKeyMode = 'enter' | 'meta_enter'
export type DefaultChatMode = 'balanced' | 'fast' | 'research' | 'rag'

export interface UserPreferences {
  appearance: AppearanceMode
  language: InterfaceLanguage
  compactSidebar: boolean
  desktopNotifications: boolean
  researchConfirmations: boolean
  rememberOpenPanels: boolean
  appIntegrations: boolean
  sendKeyMode: SendKeyMode
  defaultChatMode: DefaultChatMode
  messageFontScale: number
}

const STORAGE_KEY = 'llm_test_user_preferences_v1'

export const defaultUserPreferences: UserPreferences = {
  appearance: 'system',
  language: 'zh-CN',
  compactSidebar: false,
  desktopNotifications: false,
  researchConfirmations: true,
  rememberOpenPanels: true,
  appIntegrations: true,
  sendKeyMode: 'enter',
  defaultChatMode: 'balanced',
  messageFontScale: 1,
}

export function useUserPreferences() {
  const [preferences, setPreferences] = useState<UserPreferences>(() => loadUserPreferences())

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences))
    document.documentElement.dataset.appearance = preferences.appearance
    document.documentElement.lang = preferences.language
    document.documentElement.style.setProperty('--message-font-scale', String(preferences.messageFontScale))
  }, [preferences])

  function updatePreferences(next: Partial<UserPreferences>) {
    setPreferences((current) => ({
      ...current,
      ...next,
    }))
  }

  return {
    preferences,
    updatePreferences,
  }
}

function loadUserPreferences(): UserPreferences {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return defaultUserPreferences
    const parsed = JSON.parse(raw) as Partial<UserPreferences>
    return {
      ...defaultUserPreferences,
      appearance: normalizeAppearance(parsed.appearance),
      language: normalizeLanguage(parsed.language),
      compactSidebar: Boolean(parsed.compactSidebar),
      desktopNotifications: Boolean(parsed.desktopNotifications),
      researchConfirmations: parsed.researchConfirmations ?? defaultUserPreferences.researchConfirmations,
      rememberOpenPanels: parsed.rememberOpenPanels ?? defaultUserPreferences.rememberOpenPanels,
      appIntegrations: parsed.appIntegrations ?? defaultUserPreferences.appIntegrations,
      sendKeyMode: normalizeSendKeyMode(parsed.sendKeyMode),
      defaultChatMode: normalizeDefaultChatMode(parsed.defaultChatMode),
      messageFontScale: normalizeMessageFontScale(parsed.messageFontScale),
    }
  } catch {
    return defaultUserPreferences
  }
}

function normalizeAppearance(value: unknown): AppearanceMode {
  return value === 'light' || value === 'focus' || value === 'system' ? value : defaultUserPreferences.appearance
}

function normalizeLanguage(value: unknown): InterfaceLanguage {
  return value === 'en-US' || value === 'zh-CN' ? value : defaultUserPreferences.language
}

function normalizeSendKeyMode(value: unknown): SendKeyMode {
  return value === 'enter' || value === 'meta_enter' ? value : defaultUserPreferences.sendKeyMode
}

function normalizeDefaultChatMode(value: unknown): DefaultChatMode {
  return value === 'balanced' || value === 'fast' || value === 'research' || value === 'rag'
    ? value
    : defaultUserPreferences.defaultChatMode
}

function normalizeMessageFontScale(value: unknown): number {
  const next = Number(value)
  if (!Number.isFinite(next)) return defaultUserPreferences.messageFontScale
  return Math.min(1.25, Math.max(0.9, next))
}
