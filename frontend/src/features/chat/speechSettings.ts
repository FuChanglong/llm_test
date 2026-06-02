import { useEffect, useState } from 'react'

export interface SpeechPlaybackSettings {
  autoReadReply: boolean
  voice: string
  rate: number
}

export interface SpeechVoiceOption {
  label: string
  value: string
}

export const speechVoiceOptions: SpeechVoiceOption[] = [
  { label: '晓晓 女声', value: 'zh-CN-XiaoxiaoNeural' },
  { label: '云希 男声', value: 'zh-CN-YunxiNeural' },
  { label: '晓伊 女声', value: 'zh-CN-XiaoyiNeural' },
  { label: '云健 男声', value: 'zh-CN-YunjianNeural' },
  { label: '晓辰 女声', value: 'zh-CN-XiaochenNeural' },
  { label: '云夏 男声', value: 'zh-CN-YunxiaNeural' },
]

const STORAGE_KEY = 'llm_test_speech_playback_settings_v1'

export const defaultSpeechPlaybackSettings: SpeechPlaybackSettings = {
  autoReadReply: false,
  voice: 'zh-CN-XiaoxiaoNeural',
  rate: 1,
}

export function useSpeechPlaybackSettings() {
  const [settings, setSettings] = useState<SpeechPlaybackSettings>(() => loadSpeechPlaybackSettings())

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
  }, [settings])

  function updateSettings(next: Partial<SpeechPlaybackSettings>) {
    setSettings((current) => ({
      ...current,
      ...next,
    }))
  }

  return {
    settings,
    updateSettings,
  }
}

function loadSpeechPlaybackSettings(): SpeechPlaybackSettings {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return defaultSpeechPlaybackSettings
    const parsed = JSON.parse(raw) as Partial<SpeechPlaybackSettings>
    return {
      autoReadReply: Boolean(parsed.autoReadReply),
      voice: parsed.voice || defaultSpeechPlaybackSettings.voice,
      rate: normalizeRate(parsed.rate),
    }
  } catch {
    return defaultSpeechPlaybackSettings
  }
}

function normalizeRate(rate: unknown): number {
  const value = Number(rate)
  if (!Number.isFinite(value)) return defaultSpeechPlaybackSettings.rate
  return Math.max(0.5, Math.min(2, value))
}
