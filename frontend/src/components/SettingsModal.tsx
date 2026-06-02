import React, { useRef, useState } from 'react'
import { Button, Drawer, Modal, Select, Slider, Switch, Typography, message } from 'antd'
import {
  AppstoreOutlined,
  BellOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  LockOutlined,
  SoundOutlined,
  UserOutlined,
} from '@ant-design/icons'
import type { SpeechPlaybackSettings } from '@/features/chat/speechSettings'
import { speechVoiceOptions } from '@/features/chat/speechSettings'
import { defaultUserPreferences, type UserPreferences } from '@/features/settings/useUserPreferences'

const { Text } = Typography

type SettingsSection = 'general' | 'notifications' | 'personalization' | 'apps' | 'data' | 'security' | 'voice'

interface SettingsModalProps {
  open: boolean
  mobile: boolean
  userName: string
  speechSettings: SpeechPlaybackSettings
  preferences: UserPreferences
  onClose: () => void
  onSpeechSettingsChange: (next: Partial<SpeechPlaybackSettings>) => void
  onPreferencesChange: (next: Partial<UserPreferences>) => void
  onOpenMemory: () => void
  onOpenRagDebug: () => void
  onLogout: () => void
}

const sections: Array<{ key: SettingsSection; label: string; icon: React.ReactNode }> = [
  { key: 'general', label: '常规', icon: <UserOutlined /> },
  { key: 'notifications', label: '通知', icon: <BellOutlined /> },
  { key: 'personalization', label: '个性化', icon: <ClockCircleOutlined /> },
  { key: 'apps', label: '应用', icon: <AppstoreOutlined /> },
  { key: 'data', label: '数据管理', icon: <DatabaseOutlined /> },
  { key: 'security', label: '安全', icon: <LockOutlined /> },
  { key: 'voice', label: '语音', icon: <SoundOutlined /> },
]

const SettingsModal: React.FC<SettingsModalProps> = ({
  open,
  mobile,
  userName,
  speechSettings,
  preferences,
  onClose,
  onSpeechSettingsChange,
  onPreferencesChange,
  onOpenMemory,
  onOpenRagDebug,
  onLogout,
}) => {
  const [activeSection, setActiveSection] = useState<SettingsSection>('general')
  const importInputRef = useRef<HTMLInputElement | null>(null)
  const content = (
    <div className="settings-shell">
      <nav className="settings-nav" aria-label="设置分类">
        {sections.map((section) => (
          <button
            key={section.key}
            type="button"
            className={activeSection === section.key ? 'settings-nav-item active' : 'settings-nav-item'}
            onClick={() => setActiveSection(section.key)}
          >
            {section.icon}
            <span>{section.label}</span>
          </button>
        ))}
      </nav>
      <section className="settings-content">
        {renderSection()}
      </section>
    </div>
  )

  if (mobile) {
    return (
      <Drawer
        title="设置"
        open={open}
        onClose={onClose}
        placement="right"
        width="100%"
        className="settings-drawer"
      >
        {content}
      </Drawer>
    )
  }

  return (
    <Modal
      title="设置"
      open={open}
      onCancel={onClose}
      footer={null}
      width={880}
      className="settings-modal"
    >
      {content}
    </Modal>
  )

  function renderSection() {
    if (activeSection === 'voice') {
      return (
        <div className="settings-section">
          <SettingsRow title="启用听写" description="在聊天输入框中使用语音输入。">
            <Switch checked={preferences.appIntegrations} onChange={(checked) => onPreferencesChange({ appIntegrations: checked })} />
          </SettingsRow>
          <SettingsRow title="自动朗读" description="回复生成时自动朗读已完成的句段。">
            <Switch checked={speechSettings.autoReadReply} onChange={(checked) => onSpeechSettingsChange({ autoReadReply: checked })} />
          </SettingsRow>
          <SettingsRow title="朗读音色">
            <Select
              value={speechSettings.voice}
              options={speechVoiceOptions}
              onChange={(value) => onSpeechSettingsChange({ voice: String(value) })}
              className="settings-control"
            />
          </SettingsRow>
          <div className="settings-row vertical">
            <div className="settings-row-copy">
              <strong>朗读速度</strong>
              <Text type="secondary">{speechSettings.rate.toFixed(2)}x</Text>
            </div>
            <Slider min={0.5} max={2} step={0.1} value={speechSettings.rate} onChange={(value) => onSpeechSettingsChange({ rate: Number(value) })} />
          </div>
        </div>
      )
    }

    if (activeSection === 'data') {
      return (
        <div className="settings-section">
          <SettingsRow title="Memory 管理" description="查看、启用或删除长期记忆。">
            <Button onClick={onOpenMemory}>打开</Button>
          </SettingsRow>
          <SettingsRow title="RAG 调试" description="检查文档索引、检索结果和重建状态。">
            <Button onClick={onOpenRagDebug}>打开</Button>
          </SettingsRow>
          <SettingsRow title="保留面板状态" description="返回工作台时记住最近使用的工具抽屉。">
            <Switch checked={preferences.rememberOpenPanels} onChange={(checked) => onPreferencesChange({ rememberOpenPanels: checked })} />
          </SettingsRow>
          <SettingsRow title="导出设置" description="把当前本地偏好导出为 JSON 备份。">
            <Button onClick={exportPreferences}>导出</Button>
          </SettingsRow>
          <SettingsRow title="导入设置" description="从备份文件恢复本地偏好。">
            <Button onClick={() => importInputRef.current?.click()}>导入</Button>
          </SettingsRow>
          <SettingsRow title="重置设置" description="恢复为默认偏好，不影响账户和工作区数据。">
            <Button danger onClick={() => onPreferencesChange(defaultUserPreferences)}>恢复默认</Button>
          </SettingsRow>
          <input ref={importInputRef} type="file" accept="application/json" hidden onChange={(event) => void importPreferences(event.target.files?.[0] ?? null)} />
        </div>
      )
    }

    if (activeSection === 'general') {
      return (
        <div className="settings-section">
          <SettingsRow title="当前账户" description={userName}>
            <Button danger onClick={onLogout}>退出登录</Button>
          </SettingsRow>
          <SettingsRow title="外观" description="跟随系统外观。">
            <Select
              value={preferences.appearance}
              options={[
                { value: 'system', label: '系统' },
                { value: 'light', label: '明亮' },
                { value: 'focus', label: '专注' },
              ]}
              className="settings-control"
              onChange={(value) => onPreferencesChange({ appearance: value })}
            />
          </SettingsRow>
          <SettingsRow title="语言" description="界面语言。">
            <Select
              value={preferences.language}
              options={[
                { value: 'zh-CN', label: '简体中文' },
                { value: 'en-US', label: 'English' },
              ]}
              className="settings-control"
              onChange={(value) => onPreferencesChange({ language: value })}
            />
          </SettingsRow>
          <SettingsRow title="紧凑侧边栏" description="降低导航间距，适合小屏或高密度工作。">
            <Switch checked={preferences.compactSidebar} onChange={(checked) => onPreferencesChange({ compactSidebar: checked })} />
          </SettingsRow>
          <SettingsRow title="发送快捷键" description="控制回车是否直接发送。">
            <Select
              value={preferences.sendKeyMode}
              options={[
                { value: 'enter', label: 'Enter 发送' },
                { value: 'meta_enter', label: 'Cmd/Ctrl + Enter 发送' },
              ]}
              className="settings-control"
              onChange={(value) => onPreferencesChange({ sendKeyMode: value })}
            />
          </SettingsRow>
        </div>
      )
    }

    if (activeSection === 'notifications') {
      return (
        <div className="settings-section">
          <SettingsRow title="桌面通知" description="长任务完成或索引失败时显示浏览器通知。">
            <Switch checked={preferences.desktopNotifications} onChange={(checked) => void updateDesktopNotifications(checked)} />
          </SettingsRow>
          <SettingsRow title="研究确认" description="Deep Research 前保留确认提示，避免误触较慢任务。">
            <Switch checked={preferences.researchConfirmations} onChange={(checked) => onPreferencesChange({ researchConfirmations: checked })} />
          </SettingsRow>
          <SettingsRow title="测试通知" description="确认当前浏览器是否允许通知弹出。">
            <Button onClick={() => void sendNotificationPreview()}>发送测试通知</Button>
          </SettingsRow>
        </div>
      )
    }

    if (activeSection === 'personalization') {
      return (
        <div className="settings-section">
          <SettingsRow title="默认模式" description="新进入工作台时默认使用的回答模式。">
            <Select
              value={preferences.defaultChatMode}
              options={[
                { value: 'balanced', label: '平衡' },
                { value: 'fast', label: '快速' },
                { value: 'research', label: '研究' },
                { value: 'rag', label: '知识库' },
              ]}
              className="settings-control"
              onChange={(value) => onPreferencesChange({ defaultChatMode: value })}
            />
          </SettingsRow>
          <SettingsRow title="个性化记忆" description="通过 Memory 面板管理长期偏好和背景信息。">
            <Button onClick={onOpenMemory}>打开 Memory</Button>
          </SettingsRow>
          <div className="settings-row vertical">
            <div className="settings-row-copy">
              <strong>消息字号</strong>
              <Text type="secondary">{Math.round(preferences.messageFontScale * 100)}%</Text>
            </div>
            <Slider
              min={0.9}
              max={1.25}
              step={0.05}
              value={preferences.messageFontScale}
              onChange={(value) => onPreferencesChange({ messageFontScale: Number(value) })}
            />
          </div>
        </div>
      )
    }

    if (activeSection === 'apps') {
      return (
        <div className="settings-section">
          <SettingsRow title="启用工具入口" description="控制 Research、Image Studio、Canvas 等工具在输入框中可见。">
            <Switch checked={preferences.appIntegrations} onChange={(checked) => onPreferencesChange({ appIntegrations: checked })} />
          </SettingsRow>
          <SettingsRow title="工具权限" description="联网搜索、图片和语音能力仍会走后端鉴权。">
            <Button onClick={onOpenRagDebug}>查看状态</Button>
          </SettingsRow>
        </div>
      )
    }

    if (activeSection === 'security') {
      return (
        <div className="settings-section">
          <SettingsRow title="会话 Cookie" description="当前登录态由 HttpOnly Cookie 维护。">
            <Button danger onClick={onLogout}>退出全部本机会话</Button>
          </SettingsRow>
          <SettingsRow title="工作区隔离" description="后端会在每次请求校验用户是否属于当前工作区。">
            <Button onClick={onOpenRagDebug}>检查数据面板</Button>
          </SettingsRow>
        </div>
      )
    }

    return null
  }

  async function updateDesktopNotifications(checked: boolean) {
    if (!checked) {
      onPreferencesChange({ desktopNotifications: false })
      return
    }
    if (!(typeof window !== 'undefined' && 'Notification' in window)) {
      message.error('当前浏览器不支持桌面通知')
      return
    }
    if (Notification.permission === 'granted') {
      onPreferencesChange({ desktopNotifications: true })
      return
    }
    const permission = await Notification.requestPermission()
    if (permission === 'granted') {
      onPreferencesChange({ desktopNotifications: true })
      message.success('已启用桌面通知')
      return
    }
    onPreferencesChange({ desktopNotifications: false })
    message.warning('浏览器未授予通知权限')
  }

  async function sendNotificationPreview() {
    if (!preferences.desktopNotifications) {
      message.info('请先启用桌面通知')
      return
    }
    if (!(typeof window !== 'undefined' && 'Notification' in window) || Notification.permission !== 'granted') {
      message.warning('当前浏览器没有通知权限')
      return
    }
    const notification = new Notification('知识库问答工作台', {
      body: '这是一条通知测试，用来确认长任务完成提醒是否可用。',
    })
    window.setTimeout(() => notification.close(), 4000)
  }

  function exportPreferences() {
    const blob = new Blob([JSON.stringify(preferences, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'llm-test-preferences.json'
    link.click()
    URL.revokeObjectURL(url)
    message.success('设置已导出')
  }

  async function importPreferences(file: File | null) {
    if (!file) return
    try {
      const raw = await file.text()
      const parsed = JSON.parse(raw) as Partial<UserPreferences>
      onPreferencesChange(parsed)
      message.success('设置已导入')
    } catch {
      message.error('设置文件无法解析，请检查 JSON 格式')
    }
  }
}

interface SettingsRowProps {
  title: string
  description?: string
  children: React.ReactNode
}

const SettingsRow: React.FC<SettingsRowProps> = ({ title, description, children }) => (
  <div className="settings-row">
    <div className="settings-row-copy">
      <strong>{title}</strong>
      {description && <Text type="secondary">{description}</Text>}
    </div>
    <div className="settings-row-control">{children}</div>
  </div>
)

export default SettingsModal
