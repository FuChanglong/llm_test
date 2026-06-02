import React, { useEffect, useMemo, useState } from 'react'
import { Button, Drawer, Input, Select, Space, Typography, message } from 'antd'
import { CopyOutlined, UndoOutlined } from '@ant-design/icons'
import { getErrorMessage } from '@/api/errors'
import { getCanvas, transformCanvas, updateCanvas } from '@/api/localFeatures'

interface CanvasDrawerProps {
  open: boolean
  workspaceId: string | null
  sessionId: string | null
  seedContent: string
  onClose: () => void
  onSeedConsumed: () => void
}

type TransformMode = 'polish' | 'summarize' | 'rewrite' | 'expand'

const CanvasDrawer: React.FC<CanvasDrawerProps> = ({
  open,
  workspaceId,
  sessionId,
  seedContent,
  onClose,
  onSeedConsumed,
}) => {
  const [title, setTitle] = useState('未命名文档')
  const [content, setContent] = useState(seedContent)
  const [instruction, setInstruction] = useState('')
  const [mode, setMode] = useState<TransformMode>('rewrite')
  const [loading, setLoading] = useState(false)
  const [lastTransformedContent, setLastTransformedContent] = useState('')

  const draftKey = useMemo(() => (workspaceId && sessionId ? `canvas_draft_${workspaceId}_${sessionId}` : null), [sessionId, workspaceId])
  const contentMetrics = useMemo(() => {
    const characters = content.trim().length
    const words = content.trim() ? content.trim().split(/\s+/).length : 0
    const minutes = Math.max(1, Math.round(characters / 450))
    return { characters, words, minutes }
  }, [content])

  useEffect(() => {
    if (!draftKey) return
    try {
      window.localStorage.setItem(draftKey, JSON.stringify({ title, content }))
    } catch {
      // ignore storage failure
    }
  }, [content, draftKey, title])

  async function loadCanvas(nextSessionId: string) {
    if (!workspaceId) return
    setLoading(true)
    try {
      const canvas = await getCanvas(workspaceId, nextSessionId)
      const cachedDraft = readDraft(draftKey)
      setTitle(cachedDraft?.title || canvas.title)
      setContent(seedContent || cachedDraft?.content || canvas.content)
      if (seedContent) onSeedConsumed()
    } catch (err) {
      message.error(`加载 Canvas 失败: ${getErrorMessage(err)}`)
    } finally {
      setLoading(false)
    }
  }

  async function saveCanvas() {
    if (!workspaceId || !sessionId) return
    setLoading(true)
    try {
      await updateCanvas(workspaceId, sessionId, { title, content })
      message.success('Canvas 已保存')
    } catch (err) {
      message.error(`保存 Canvas 失败: ${getErrorMessage(err)}`)
    } finally {
      setLoading(false)
    }
  }

  async function runTransform() {
    if (!workspaceId || !sessionId || !content.trim()) return
    setLoading(true)
    try {
      setLastTransformedContent(content)
      const next = await transformCanvas(workspaceId, sessionId, {
        content,
        instruction: instruction.trim() || '按默认方式处理',
        mode,
      })
      setContent(next)
    } catch (err) {
      message.error(`处理 Canvas 失败: ${getErrorMessage(err)}`)
    } finally {
      setLoading(false)
    }
  }

  async function copyContent() {
    try {
      await navigator.clipboard.writeText(content)
      message.success('Canvas 内容已复制')
    } catch {
      message.error('复制 Canvas 失败')
    }
  }

  function exportMarkdown() {
    const blob = new Blob([`# ${title}\n\n${content}`], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${sanitizeFilename(title || 'canvas')}.md`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <Drawer
      title="Canvas 文档编辑区"
      open={open}
      onClose={onClose}
      afterOpenChange={(visible) => {
        if (visible && workspaceId && sessionId) void loadCanvas(sessionId)
      }}
      width={760}
      className="workspace-surface-drawer"
    >
      {!workspaceId || !sessionId ? (
        <Typography.Text type="secondary">请先选择或创建一个会话。</Typography.Text>
      ) : (
        <div className="canvas-panel">
          <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="文档标题" />
          <Space wrap className="canvas-meta-row">
            <Typography.Text type="secondary">{contentMetrics.characters.toLocaleString()} 字符</Typography.Text>
            <Typography.Text type="secondary">{contentMetrics.words.toLocaleString()} 词</Typography.Text>
            <Typography.Text type="secondary">预计 {contentMetrics.minutes} 分钟阅读</Typography.Text>
          </Space>
          <Input.TextArea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            autoSize={{ minRows: 16, maxRows: 28 }}
            placeholder="在这里编辑长文，或从回答发送到 Canvas"
          />
          <Space.Compact className="canvas-tools">
            <Select
              value={mode}
              onChange={setMode}
              options={[
                { value: 'polish', label: '润色' },
                { value: 'summarize', label: '总结' },
                { value: 'rewrite', label: '改写' },
                { value: 'expand', label: '扩写' },
              ]}
            />
            <Input
              value={instruction}
              onChange={(event) => setInstruction(event.target.value)}
              placeholder="补充要求，比如更正式、面向客户、缩短到 300 字"
            />
            <Button loading={loading} onClick={runTransform}>
              执行
            </Button>
          </Space.Compact>
          <Space wrap>
            <Button type="primary" loading={loading} onClick={saveCanvas}>
              保存 Canvas
            </Button>
            <Button icon={<CopyOutlined />} onClick={() => void copyContent()}>
              复制正文
            </Button>
            <Button onClick={exportMarkdown}>导出 Markdown</Button>
            <Button icon={<UndoOutlined />} disabled={!lastTransformedContent} onClick={() => setContent(lastTransformedContent)}>
              撤回上次变换
            </Button>
          </Space>
        </div>
      )}
    </Drawer>
  )
}

function sanitizeFilename(value: string) {
  return value.replace(/[\\/:*?"<>|]+/g, '_')
}

function readDraft(key: string | null) {
  if (!key) return null
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw) as { title?: string; content?: string }
    return {
      title: parsed.title || '',
      content: parsed.content || '',
    }
  } catch {
    return null
  }
}

export default CanvasDrawer
