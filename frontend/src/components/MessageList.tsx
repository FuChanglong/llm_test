import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, Dropdown, Empty, Input, Space, Tag, Tooltip, Typography, message } from 'antd'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { AudioOutlined, CopyOutlined, EditOutlined, FileTextOutlined, MoreOutlined, RedoOutlined, SaveOutlined } from '@ant-design/icons'
import { Howl } from 'howler'
import type { SessionDetail } from '@/api/session'
import type { ChatMessage, ChatSource, ReasoningStep } from '@/api/chat'
import { synthesizeSpeech } from '@/api/localFeatures'
import type { SpeechPlaybackSettings } from '@/features/chat/speechSettings'

interface MessageListProps {
  currentSession: SessionDetail | null
  onFillPrompt: (prompt: string) => void
  onEditMessage: (messageId: string, content: string) => void
  onRegenerateMessage: (messageId: string) => void
  onSendToCanvas: (content: string) => void
  onSaveMemory: (content: string) => void
  speechSettings: SpeechPlaybackSettings
  isStreamingReply: boolean
  mobile: boolean
  fontScale: number
}

const EXAMPLE_PROMPTS = [
  '梳理这个项目当前的核心能力，并给出下一步产品建议',
  '帮我检索本地知识库里 RAG 的实现链路，并总结关键模块',
  '基于当前会话内容，产出一份可执行的开发计划',
]

const MessageList: React.FC<MessageListProps> = ({
  currentSession,
  onFillPrompt,
  onEditMessage,
  onRegenerateMessage,
  onSendToCanvas,
  onSaveMemory,
  speechSettings,
  isStreamingReply,
  mobile,
  fontScale,
}) => {
  const { Text } = Typography
  const sessionMessages = currentSession?.messages
  const sortedMessages = sessionMessages ?? []
  const bottomRef = useRef<HTMLDivElement>(null)
  const [expandedReasoning, setExpandedReasoning] = useState<Set<string>>(new Set())
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set())
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [playingMessageKey, setPlayingMessageKey] = useState<string | null>(null)
  const [loadingSpeechKey, setLoadingSpeechKey] = useState<string | null>(null)
  const activeAudioRef = useRef<Howl | null>(null)
  const activeAudioUrlRef = useRef<string | null>(null)
  const speechQueueRef = useRef<Array<{ messageKey: string; text: string }>>([])
  const processingSpeechRef = useRef(false)
  const autoSpeechProgressRef = useRef<Record<string, { spokenCount: number; flushedTail: boolean }>>({})
  const markdownComponents = useMemo(
    () => ({
      a: ({ href, children }: { href?: string; children?: React.ReactNode }) => (
        <button
          type="button"
          className="markdown-link"
          onClick={() => openExternalLink(href)}
          disabled={!href}
        >
          {children}
        </button>
      ),
      code: ({ className, children }: { className?: string; children?: React.ReactNode }) => {
        const codeText = extractTextContent(children).replace(/\n$/, '')
        const isBlock = Boolean(className)
        if (!isBlock) {
          return <code className={className}>{children}</code>
        }
        return (
          <div className="code-block">
            <div className="code-block-toolbar">
              <Button
                type="text"
                size="small"
                icon={<CopyOutlined />}
                className="code-copy-btn"
                onClick={() => void copyMessage(codeText)}
              >
                复制
              </Button>
            </div>
            <code className={className}>{children}</code>
          </div>
        )
      },
    }),
    [],
  )

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [sessionMessages])

  async function copyMessage(content: string) {
    try {
      await navigator.clipboard.writeText(content)
      message.success('已复制')
    } catch {
      message.error('复制失败')
    }
  }

  useEffect(() => {
    return () => {
      speechQueueRef.current = []
      activeAudioRef.current?.unload()
      if (activeAudioUrlRef.current) URL.revokeObjectURL(activeAudioUrlRef.current)
    }
  }, [])

  useEffect(() => {
    speechQueueRef.current = []
    processingSpeechRef.current = false
    autoSpeechProgressRef.current = {}
    activeAudioRef.current?.stop()
    activeAudioRef.current?.unload()
    activeAudioRef.current = null
    if (activeAudioUrlRef.current) {
      URL.revokeObjectURL(activeAudioUrlRef.current)
      activeAudioUrlRef.current = null
    }
    const timer = window.setTimeout(() => {
      setPlayingMessageKey(null)
      setLoadingSpeechKey(null)
    }, 0)
    return () => window.clearTimeout(timer)
  }, [currentSession?.id])

  useEffect(() => {
    if (!speechSettings.autoReadReply || !currentSession?.messages?.length) return
    const latestAssistant = [...currentSession.messages].reverse().find((item) => item.role === 'assistant' && item.content.trim())
    if (!latestAssistant) return
    const latestIndex = currentSession.messages.lastIndexOf(latestAssistant)
    const messageKey = latestAssistant.id ?? `${latestAssistant.time}-${latestIndex}`
    const progress = autoSpeechProgressRef.current[messageKey] ?? { spokenCount: 0, flushedTail: false }
    const { segments, trailing } = splitSpeechSegments(latestAssistant.content)
    const newSegments = segments.slice(progress.spokenCount)
    let nextProgress = progress
    if (newSegments.length > 0 && (isStreamingReply || latestAssistant.status === 'streaming' || progress.spokenCount > 0)) {
      nextProgress = { ...nextProgress, spokenCount: segments.length }
      enqueueSpeech(messageKey, newSegments)
    }
    if (latestAssistant.status === 'done' && !progress.flushedTail && trailing) {
      nextProgress = { ...nextProgress, flushedTail: true }
      enqueueSpeech(messageKey, [trailing])
    }
    autoSpeechProgressRef.current[messageKey] = nextProgress
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentSession?.messages, isStreamingReply, speechSettings.autoReadReply])

  async function speakMessage(messageKey: string, content: string) {
    if (playingMessageKey === messageKey) {
      stopSpeechPlayback()
      return
    }
    stopSpeechPlayback()
    enqueueSpeech(messageKey, [content])
  }

  if (!currentSession) {
    return (
      <div className="messages">
        <Empty description="选择一个会话或创建新会话" />
      </div>
    )
  }

  return (
    <div className="messages" style={{ fontSize: `${fontScale}rem` }}>
      {currentSession.summary && (
        <Card size="small" className="summary-card">
          <Text strong>长期记忆摘要</Text>
          <div className="markdown-body summary-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {normalizeBareUrlsForMarkdown(currentSession.summary)}
            </ReactMarkdown>
          </div>
        </Card>
      )}
      {sortedMessages.length === 0 ? (
        <div className="welcome-state">
          <div className="welcome-kicker">Intelligent Workspace</div>
          <h1>面向研究与知识工程的本地工作台</h1>
          <p>统一处理知识库检索、长文编辑、研究分析与会话记忆，不依赖复杂外部平台。</p>
          <div className="welcome-band">
            <article className="welcome-band-card">
              <strong>Knowledge Retrieval</strong>
              <span>本地资料、附件内容与引用证据联动输出</span>
            </article>
            <article className="welcome-band-card">
              <strong>Research Workflow</strong>
              <span>联网搜索、网页归纳、研究摘要与后续追问衔接</span>
            </article>
            <article className="welcome-band-card">
              <strong>Authoring Surface</strong>
              <span>Canvas、Memory 与导出能力服务完整交付流程</span>
            </article>
          </div>
          <div className="prompt-grid">
            {EXAMPLE_PROMPTS.map((prompt) => (
              <button key={prompt} type="button" className="prompt-card" onClick={() => onFillPrompt(prompt)}>
                {prompt}
              </button>
            ))}
          </div>
        </div>
      ) : (
        sortedMessages.map((msg, idx) => renderMessage(msg, idx))
      )}
      <div ref={bottomRef} />
    </div>
  )

  function renderMessage(msg: ChatMessage, idx: number) {
    const messageKey = msg.id ?? `${msg.time}-${idx}`
    const waiting = msg.role === 'assistant' && msg.status === 'streaming' && !msg.content.trim()
    const hasReasoning = msg.role === 'assistant' && !!msg.reasoning?.length
    const reasoningOpen = hasReasoning && expandedReasoning.has(messageKey)
    const isEditing = msg.id && editingId === msg.id
    return (
      <div key={messageKey} className={`msg ${msg.role} ${msg.status ?? ''}`}>
        <div className="msg-stack">
          <div className="msg-bubble">
            <div className={`msg-content ${msg.role === 'user' ? 'user' : 'assistant'}`}>
              {hasReasoning && renderReasoning(messageKey, waiting, reasoningOpen, msg.reasoning ?? [])}
              {waiting ? (
                <div className="typing-indicator" aria-label="正在处理">
                  <span />
                  <span />
                  <span />
                </div>
              ) : isEditing ? (
                <div className="message-edit-box">
                  <Input.TextArea
                    value={editDraft}
                    autoSize={{ minRows: 2, maxRows: 8 }}
                    onChange={(event) => setEditDraft(event.target.value)}
                  />
                  <Space>
                    <Button
                      type="primary"
                      size="small"
                      onClick={() => {
                        onEditMessage(msg.id as string, editDraft)
                        setEditingId(null)
                      }}
                    >
                      保存并重发
                    </Button>
                    <Button size="small" onClick={() => setEditingId(null)}>
                      取消
                    </Button>
                  </Space>
                </div>
              ) : msg.role === 'assistant' ? (
                <div className="markdown-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                    {normalizeBareUrlsForMarkdown(msg.content)}
                  </ReactMarkdown>
                </div>
              ) : (
                msg.content
              )}
              {msg.attachments?.length ? (
                <div className="message-attachments">
                  {msg.attachments.map((attachment) => (
                    <Tag key={attachment.id}>{attachment.filename}</Tag>
                  ))}
                </div>
              ) : null}
              {msg.role === 'assistant' && msg.sources?.length ? renderSources(messageKey, msg.sources) : null}
            </div>
          </div>
          {msg.content.trim() && (
            <div className="message-actions">
              <Tooltip title="复制">
                <Button
                  type="text"
                  size="small"
                  icon={<CopyOutlined />}
                  className="msg-copy-btn"
                  onClick={() => copyMessage(msg.content)}
                />
              </Tooltip>
              {msg.role === 'user' && msg.id && (
                <Tooltip title="编辑并重发">
                  <Button
                    type="text"
                    size="small"
                    icon={<EditOutlined />}
                    className="msg-copy-btn"
                    onClick={() => {
                      setEditingId(msg.id ?? null)
                      setEditDraft(msg.content)
                    }}
                  />
                </Tooltip>
              )}
              {msg.role === 'assistant' && msg.id && (
                <Tooltip title="重新生成">
                  <Button
                    type="text"
                    size="small"
                    icon={<RedoOutlined />}
                    className="msg-copy-btn"
                    onClick={() => onRegenerateMessage(msg.id as string)}
                  />
                </Tooltip>
              )}
              {msg.role === 'assistant' && (
                <>
                  <Tooltip title="朗读">
                    <Button
                      type="text"
                      size="small"
                      icon={<AudioOutlined />}
                      className="msg-copy-btn"
                      loading={loadingSpeechKey === messageKey}
                      onClick={() => void speakMessage(messageKey, msg.content)}
                    />
                  </Tooltip>
                </>
              )}
              {msg.role === 'assistant' && (
                <Dropdown
                  trigger={['click']}
                  placement={mobile ? 'topRight' : 'bottomLeft'}
                  menu={{
                    items: [
                      { key: 'canvas', icon: <FileTextOutlined />, label: '发送到 Canvas' },
                      { key: 'memory', icon: <SaveOutlined />, label: '保存为 Memory' },
                    ],
                    onClick: ({ key }) => {
                      if (key === 'canvas') onSendToCanvas(msg.content)
                      if (key === 'memory') onSaveMemory(msg.content)
                    },
                  }}
                >
                  <Button type="text" size="small" icon={<MoreOutlined />} className="msg-copy-btn" />
                </Dropdown>
              )}
            </div>
          )}
        </div>
      </div>
    )
  }

  function renderReasoning(messageKey: string, waiting: boolean, reasoningOpen: boolean, reasoning: ReasoningStep[]) {
    return reasoningOpen ? (
      <div className="reasoning-panel">
        <button
          type="button"
          className="reasoning-toggle"
          aria-expanded="true"
          onClick={() => toggleSet(expandedReasoning, setExpandedReasoning, messageKey)}
          disabled={waiting}
        >
          <span>{waiting ? '处理中' : '处理过程'}</span>
          {!waiting && <span>收起</span>}
        </button>
        {reasoning.map((step, stepIndex) => (
          <div key={`${step.type}-${stepIndex}`} className={`reasoning-step ${step.type}`}>
            {formatReasoningStep(step)}
          </div>
        ))}
      </div>
    ) : (
      <button
        type="button"
        className="reasoning-collapsed"
        aria-expanded="false"
        onClick={() => toggleSet(expandedReasoning, setExpandedReasoning, messageKey)}
      >
        查看处理过程
      </button>
    )
  }

  function renderSources(messageKey: string, sources: ChatSource[]) {
    const open = expandedSources.has(messageKey)
    const dedupedSources = dedupeDisplaySources(sources)
    const visible = open ? dedupedSources : dedupedSources.slice(0, 2)
    return (
      <div className="source-panel">
        <button
          type="button"
          className="source-toggle"
          onClick={() => toggleSet(expandedSources, setExpandedSources, messageKey)}
        >
          来源 {dedupedSources.length} 条 {open ? '收起' : '展开'}
        </button>
        {visible.map((source, index) => (
          <article key={`${source.citation ?? source.source}-${index}`} className="source-card">
            <div className="source-card-title">
              <div className="source-card-link-group">
                <button
                  type="button"
                  className="source-link"
                  onClick={() => openExternalLink(source.preview_url ?? source.download_url)}
                  disabled={!source.preview_url && !source.download_url}
                >
                  {source.title ?? source.source}
                </button>
              </div>
              <Tag>{source.kind === 'attachment' ? '附件' : '知识库'}</Tag>
            </div>
          </article>
        ))}
      </div>
    )
  }

  function toggleSet(
    current: Set<string>,
    setter: React.Dispatch<React.SetStateAction<Set<string>>>,
    messageKey: string,
  ) {
    setter(() => {
      const next = new Set(current)
      if (next.has(messageKey)) {
        next.delete(messageKey)
      } else {
        next.add(messageKey)
      }
      return next
    })
  }

  function enqueueSpeech(messageKey: string, segments: string[]) {
    const cleaned = segments.map((item) => item.trim()).filter(Boolean)
    if (cleaned.length === 0) return
    speechQueueRef.current.push(...cleaned.map((text) => ({ messageKey, text })))
    if (!processingSpeechRef.current) {
      void playNextSpeech()
    }
  }

  async function playNextSpeech() {
    const next = speechQueueRef.current.shift()
    if (!next) {
      processingSpeechRef.current = false
      setPlayingMessageKey(null)
      setLoadingSpeechKey(null)
      return
    }
    processingSpeechRef.current = true
    setLoadingSpeechKey(next.messageKey)
    try {
      const audioBlob = await synthesizeSpeech(next.text, {
        voice: speechSettings.voice,
        rate: speechSettings.rate,
      })
      const audioUrl = URL.createObjectURL(audioBlob)
      activeAudioRef.current?.unload()
      if (activeAudioUrlRef.current) URL.revokeObjectURL(activeAudioUrlRef.current)
      activeAudioUrlRef.current = audioUrl
      const player = new Howl({
        src: [audioUrl],
        format: ['mp3', 'wav', 'aac', 'flac', 'ogg'],
        html5: true,
        onplay: () => {
          setPlayingMessageKey(next.messageKey)
          setLoadingSpeechKey(null)
        },
        onend: () => {
          player.unload()
          if (activeAudioUrlRef.current === audioUrl) {
            URL.revokeObjectURL(audioUrl)
            activeAudioUrlRef.current = null
          }
          activeAudioRef.current = null
          void playNextSpeech()
        },
        onloaderror: () => {
          message.error('语音加载失败')
          stopSpeechPlayback()
        },
        onplayerror: () => {
          message.error('语音播放失败')
          stopSpeechPlayback()
        },
      })
      activeAudioRef.current = player
      player.play()
    } catch (err) {
      message.error(`朗读失败: ${String(err)}`)
      stopSpeechPlayback()
    }
  }

  function stopSpeechPlayback() {
    speechQueueRef.current = []
    processingSpeechRef.current = false
    activeAudioRef.current?.stop()
    activeAudioRef.current?.unload()
    activeAudioRef.current = null
    if (activeAudioUrlRef.current) {
      URL.revokeObjectURL(activeAudioUrlRef.current)
      activeAudioUrlRef.current = null
    }
    setPlayingMessageKey(null)
    setLoadingSpeechKey(null)
  }
}

function formatReasoningStep(step: ReasoningStep): string {
  if (step.type === 'reasoning') return step.content ?? ''
  const toolName = formatToolName(step.name)
  if (step.type === 'tool_start') {
    return step.input ? `调用工具 ${toolName}：${step.input}` : `调用工具 ${toolName}`
  }
  if (step.type === 'tool_end') {
    return step.duration_ms ? `工具 ${toolName} 完成，用时 ${step.duration_ms}ms` : `工具 ${toolName} 完成`
  }
  return `工具 ${toolName} 调用失败`
}

function formatToolName(name?: string): string {
  const labels: Record<string, string> = {
    rag_search: '本地知识库',
    web_search: '网络搜索',
    langchain_docs_search: 'LangChain 文档',
    get_weather: '实时天气',
    weather_advisor: '天气建议',
    calculator: '计算器',
    current_time: '当前时间',
  }
  return name ? labels[name] ?? name : 'unknown'
}

function dedupeDisplaySources(sources: ChatSource[]): ChatSource[] {
  const seen = new Set<string>()
  const deduped: ChatSource[] = []
  for (const source of sources) {
    const key = source.preview_url ?? source.download_url ?? source.document_id ?? source.title ?? source.source
    if (!key || seen.has(key)) continue
    seen.add(key)
    deduped.push(source)
  }
  return deduped
}

function extractTextContent(node: React.ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(extractTextContent).join('')
  if (React.isValidElement<{ children?: React.ReactNode }>(node)) return extractTextContent(node.props.children)
  return ''
}

function openExternalLink(href?: string | null) {
  if (!href) return
  window.open(href, '_blank', 'noopener,noreferrer')
}

function normalizeBareUrlsForMarkdown(content: string): string {
  return content.replace(/(?<!\]\()(?<!<)(https?:\/\/[^\s<>\u3000（）「」『』【】]+)/g, '<$1>')
}

function splitSpeechSegments(content: string): { segments: string[]; trailing: string } {
  const normalized = String(content || '').replace(/\r/g, '')
  const parts = normalized.split(/(?<=[。！？!?；;：:\n])/)
  const segments = parts.map((item) => item.trim()).filter(Boolean)
  const trailing = segments.length > 0 && /[。！？!?；;：:]$/.test(segments[segments.length - 1])
    ? ''
    : (segments.pop() || '')
  return { segments, trailing }
}

export default MessageList
