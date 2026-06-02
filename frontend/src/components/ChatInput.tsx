import React, { useEffect, useRef, useState } from 'react'
import { Button, Drawer, Input, Popover, Select, Slider, Switch, Tag, Tooltip, Upload } from 'antd'
import {
  AudioOutlined,
  BarChartOutlined,
  CloseOutlined,
  DatabaseOutlined,
  DownloadOutlined,
  FileImageOutlined,
  FileTextOutlined,
  PlusOutlined,
  SendOutlined,
  SettingOutlined,
  SoundOutlined,
  StopOutlined,
} from '@ant-design/icons'
import type { ChatAttachment } from '@/api/chat'
import type { ChatMode } from '@/features/chat/useChatWorkspace'
import type { SpeechPlaybackSettings } from '@/features/chat/speechSettings'
import { speechVoiceOptions } from '@/features/chat/speechSettings'

const { TextArea } = Input

type SpeechRecognitionLike = {
  continuous: boolean
  interimResults: boolean
  lang: string
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null
  onerror: ((event: { error: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
}

declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognitionLike
    webkitSpeechRecognition?: new () => SpeechRecognitionLike
  }
}

interface ChatInputProps {
  input: string
  setInput: (value: string) => void
  loading: boolean
  currentSessionId: string | null
  chatMode: ChatMode
  toolsEnabled: boolean
  pendingAttachments: ChatAttachment[]
  onSend: () => void
  onStop: () => void
  onChatModeChange: (mode: ChatMode) => void
  onOpenResearch: () => void
  onOpenImages: () => void
  onOpenCanvas: () => void
  onOpenMemory: () => void
  onOpenRagDebug: () => void
  onExport: () => void
  mobile: boolean
  sendKeyMode: 'enter' | 'meta_enter'
  speechSettings: SpeechPlaybackSettings
  onSpeechSettingsChange: (next: Partial<SpeechPlaybackSettings>) => void
  onUploadAttachment: (file: File) => Promise<void>
  onRemoveAttachment: (attachmentId: string) => void
  onAnalyzeAttachment: (attachmentId: string) => void
}

const ChatInput: React.FC<ChatInputProps> = ({
  input,
  setInput,
  loading,
  currentSessionId,
  chatMode,
  toolsEnabled,
  pendingAttachments,
  onSend,
  onStop,
  onChatModeChange,
  onOpenResearch,
  onOpenImages,
  onOpenCanvas,
  onOpenMemory,
  onOpenRagDebug,
  onExport,
  mobile,
  sendKeyMode,
  speechSettings,
  onSpeechSettingsChange,
  onUploadAttachment,
  onRemoveAttachment,
  onAnalyzeAttachment,
}) => {
  const canSend = input.trim().length > 0 && !loading
  const [listening, setListening] = useState(false)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [speechSettingsOpen, setSpeechSettingsOpen] = useState(false)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)

  const handleKeyPress = (e: React.KeyboardEvent) => {
    const shouldSend = sendKeyMode === 'enter'
      ? !e.shiftKey && e.key === 'Enter'
      : (e.metaKey || e.ctrlKey) && e.key === 'Enter'
    if (shouldSend) {
      e.preventDefault()
      if (canSend) onSend()
    }
  }

  useEffect(() => {
    return () => {
      recognitionRef.current?.stop()
    }
  }, [])

  function toggleVoiceInput() {
    if (listening) {
      recognitionRef.current?.stop()
      setListening(false)
      return
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      return
    }
    const recognition = new SpeechRecognition()
    recognition.lang = 'zh-CN'
    recognition.continuous = true
    recognition.interimResults = true
    recognition.onresult = (event) => {
      const text = Array.from(event.results)
        .map((result) => result[0]?.transcript ?? '')
        .join('')
      setInput(text.trim())
    }
    recognition.onerror = () => {
      setListening(false)
    }
    recognition.onend = () => {
      setListening(false)
    }
    recognitionRef.current = recognition
    recognition.start()
    setListening(true)
  }

  return (
    <div className="composer">
      {pendingAttachments.length > 0 && (
        <div className="attachment-row">
          {pendingAttachments.map((attachment) => (
            <Tag key={attachment.id} className="attachment-chip">
              <span className="attachment-name">{attachment.filename}</span>
              <span className={attachment.status === 'ready' ? 'attachment-ok' : 'attachment-error'}>
                {attachment.status === 'ready' ? `${attachment.chunks} 段` : '解析失败'}
              </span>
              {isTableAttachment(attachment.filename) && (
                <Tooltip title="本地数据分析">
                  <button
                    type="button"
                    className="attachment-icon-button"
                    onClick={() => onAnalyzeAttachment(attachment.id)}
                  >
                    <BarChartOutlined />
                  </button>
                </Tooltip>
              )}
              <button
                type="button"
                className="attachment-icon-button"
                onClick={() => onRemoveAttachment(attachment.id)}
              >
                <CloseOutlined />
              </button>
            </Tag>
          ))}
        </div>
      )}
      <div className="composer-input-shell">
        <div className="composer-input-row">
          {mobile ? (
            <Button
              type="text"
              icon={<PlusOutlined />}
              className="composer-plus-button"
              onClick={() => setToolsOpen(true)}
              disabled={!toolsEnabled}
              aria-label="打开工具"
            />
          ) : (
            <Popover
              trigger="click"
              open={toolsOpen}
              onOpenChange={setToolsOpen}
              placement="topLeft"
              content={renderToolMenu()}
              overlayClassName="tool-popover"
            >
              <Button type="text" icon={<PlusOutlined />} className="composer-plus-button" disabled={!toolsEnabled} aria-label="打开工具" />
            </Popover>
          )}
          <TextArea
            className="composer-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            autoSize={{ minRows: 1, maxRows: mobile ? 5 : 6 }}
            placeholder={sendKeyMode === 'enter' ? '有问题，尽管问' : '输入内容后按 Cmd/Ctrl + Enter 发送'}
            onPressEnter={handleKeyPress}
          />
          <div className="composer-inline-actions">
            <Select
              value={chatMode}
              className="composer-mode-select"
              popupMatchSelectWidth={false}
              onChange={(value) => onChatModeChange(value as ChatMode)}
              options={[
                { value: 'balanced', label: '平衡' },
                { value: 'fast', label: '快速' },
                { value: 'research', label: '研究' },
                { value: 'rag', label: '知识库' },
              ]}
            />
            <Button
              type="text"
              icon={<AudioOutlined />}
              className={listening ? 'composer-voice-button active' : 'composer-voice-button'}
              onClick={toggleVoiceInput}
              disabled={loading || !toolsEnabled}
              aria-label={listening ? '停止语音输入' : '语音输入'}
            />
            {loading ? (
              <Button icon={<StopOutlined />} className="composer-stop-button" onClick={onStop} aria-label="停止生成" />
            ) : (
              <Button
                type="primary"
                icon={<SendOutlined />}
                className="composer-send-button"
                onClick={onSend}
                disabled={!canSend}
                aria-label="发送"
              />
            )}
          </div>
        </div>
      </div>
      <Drawer
        title="添加内容和工具"
        placement="bottom"
        height={520}
        open={mobile && toolsOpen}
        onClose={() => setToolsOpen(false)}
        className="composer-tools-drawer mobile-action-sheet"
      >
        {renderToolMenu()}
      </Drawer>
      <Drawer
        title="朗读设置"
        placement="bottom"
        height={360}
        open={speechSettingsOpen}
        onClose={() => setSpeechSettingsOpen(false)}
        className="composer-tools-drawer"
      >
        <div className="speech-settings-panel">
          <label className="speech-settings-row">
            <div>
              <strong>自动朗读</strong>
              <span>每条回复开始出现正文后，自动朗读当前已完成句段。</span>
            </div>
            <Switch
              checked={speechSettings.autoReadReply}
              onChange={(checked) => onSpeechSettingsChange({ autoReadReply: checked })}
            />
          </label>
          <div className="speech-settings-group">
            <strong>朗读音色</strong>
            <Select
              value={speechSettings.voice}
              options={speechVoiceOptions}
              onChange={(value) => onSpeechSettingsChange({ voice: String(value) })}
            />
          </div>
          <div className="speech-settings-group">
            <div className="speech-settings-rate">
              <strong>朗读速度</strong>
              <span>{speechSettings.rate.toFixed(2)}x</span>
            </div>
            <Slider
              min={0.5}
              max={2}
              step={0.1}
              value={speechSettings.rate}
              onChange={(value) => onSpeechSettingsChange({ rate: Number(value) })}
            />
          </div>
          <Button icon={<SoundOutlined />} onClick={() => setSpeechSettingsOpen(false)}>
            完成
          </Button>
        </div>
      </Drawer>
    </div>
  )

  function runToolAction(action: () => void) {
    setToolsOpen(false)
    action()
  }

  function renderToolMenu() {
    return (
      <div className="tool-menu">
        <ToolGroup title="添加内容">
          <Upload
            showUploadList={false}
            accept=".md,.txt,.doc,.docx,.pdf,.csv,.xlsx,.xls"
            disabled={!currentSessionId || loading || !toolsEnabled}
            beforeUpload={(file) => {
              setToolsOpen(false)
              void onUploadAttachment(file)
              return false
            }}
          >
            <button type="button" className="tool-menu-item" disabled={!currentSessionId || loading || !toolsEnabled}>
              <PlusOutlined />
              <span><strong>附件</strong><small>上传文档、表格或 PDF</small></span>
            </button>
          </Upload>
          <button type="button" className="tool-menu-item" onClick={() => runToolAction(onOpenImages)}>
            <FileImageOutlined />
            <span><strong>图片</strong><small>生成、编辑和分析图片</small></span>
          </button>
        </ToolGroup>
        <ToolGroup title="辅助创作">
          <button type="button" className="tool-menu-item" onClick={() => runToolAction(onOpenResearch)}>
            <DatabaseOutlined />
            <span><strong>Research</strong><small>联网搜索与深度研究</small></span>
          </button>
          <button type="button" className="tool-menu-item" onClick={() => runToolAction(onOpenCanvas)}>
            <FileTextOutlined />
            <span><strong>Canvas</strong><small>长文写作与润色编辑</small></span>
          </button>
        </ToolGroup>
        <ToolGroup title="知识与会话">
          <button type="button" className="tool-menu-item" onClick={() => runToolAction(onOpenMemory)}>
            <SoundOutlined />
            <span><strong>Memory</strong><small>管理长期记忆与偏好</small></span>
          </button>
          <button type="button" className="tool-menu-item" onClick={() => runToolAction(onOpenRagDebug)}>
            <DatabaseOutlined />
            <span><strong>RAG 调试</strong><small>查看索引和检索结果</small></span>
          </button>
          <button type="button" className="tool-menu-item" onClick={() => runToolAction(onExport)}>
            <DownloadOutlined />
            <span><strong>导出 JSON</strong><small>导出当前会话结构数据</small></span>
          </button>
          <button type="button" className="tool-menu-item" onClick={() => { setToolsOpen(false); setSpeechSettingsOpen(true) }}>
            <SettingOutlined />
            <span><strong>朗读设置</strong><small>自动朗读、语速和音色</small></span>
          </button>
        </ToolGroup>
      </div>
    )
  }
}

interface ToolGroupProps {
  title: string
  children: React.ReactNode
}

const ToolGroup: React.FC<ToolGroupProps> = ({ title, children }) => (
  <section className="tool-menu-group">
    <span>{title}</span>
    {children}
  </section>
)

function isTableAttachment(filename: string): boolean {
  return /\.(csv|xlsx|xls)$/i.test(filename)
}

export default ChatInput
