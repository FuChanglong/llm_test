import React, { useEffect, useRef, useState } from 'react'
import { Alert, Button, Drawer, Empty, Input, List, Popconfirm, Progress, Space, Tag, Typography, Upload, message } from 'antd'
import { DeleteOutlined, ReloadOutlined, SearchOutlined, UploadOutlined } from '@ant-design/icons'
import {
  deleteRagDocument,
  getRagRebuildStatus,
  listRagDocuments,
  rebuildRagIndex,
  searchRag,
  uploadRagDocument,
} from '@/api/localFeatures'
import type { RagRebuildStatus, RagSearchResult, WorkspaceDocument } from '@/api/localFeatures'

const { Text } = Typography

interface RagDebugPanelProps {
  open: boolean
  workspaceId: string | null
  onClose: () => void
}

const RagDebugPanel: React.FC<RagDebugPanelProps> = ({ open, workspaceId, onClose }) => {
  const [documents, setDocuments] = useState<WorkspaceDocument[]>([])
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<RagSearchResult[]>([])
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [loadingSearch, setLoadingSearch] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [rebuildStatus, setRebuildStatus] = useState<RagRebuildStatus | null>(null)
  const uploadChainRef = useRef<Promise<void>>(Promise.resolve())
  const statusDismissTimerRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (statusDismissTimerRef.current) window.clearTimeout(statusDismissTimerRef.current)
    }
  }, [])

  useEffect(() => {
    if (!rebuildStatus || rebuilding) return
    if (rebuildStatus.status !== 'complete' && rebuildStatus.status !== 'error') return
    if (statusDismissTimerRef.current) window.clearTimeout(statusDismissTimerRef.current)
    statusDismissTimerRef.current = window.setTimeout(() => {
      setRebuildStatus((current) => (current?.id === rebuildStatus.id ? null : current))
      statusDismissTimerRef.current = null
    }, 4000)
  }, [rebuildStatus, rebuilding])

  useEffect(() => {
    if (!rebuilding || !workspaceId) return undefined
    const refreshStatus = async () => {
      try {
        const nextStatus = await getRagRebuildStatus(workspaceId)
        setRebuildStatus(nextStatus)
        if (nextStatus.status === 'complete') {
          setRebuilding(false)
          setLoadingDocs(false)
          setDocuments(await listRagDocuments(workspaceId))
          message.success('知识库任务已完成')
        }
        if (nextStatus.status === 'error') {
          setRebuilding(false)
          setLoadingDocs(false)
          message.error(`知识库任务失败: ${nextStatus.error || nextStatus.message}`)
        }
      } catch (err) {
        setRebuilding(false)
        setLoadingDocs(false)
        message.error(`获取重建进度失败: ${String(err)}`)
      }
    }
    void refreshStatus()
    const timer = window.setInterval(() => {
      void refreshStatus()
    }, 1000)
    return () => window.clearInterval(timer)
  }, [rebuilding, workspaceId])

  async function loadDocuments() {
    if (!workspaceId) return
    setLoadingDocs(true)
    try {
      setDocuments(await listRagDocuments(workspaceId))
    } catch (err) {
      message.error(`加载 RAG 文档失败: ${String(err)}`)
    } finally {
      setLoadingDocs(false)
    }
  }

  async function rebuild() {
    if (!workspaceId) return
    setLoadingDocs(true)
    setRebuilding(true)
    setRebuildStatus(null)
    try {
      const nextStatus = await rebuildRagIndex(workspaceId)
      setRebuildStatus(nextStatus)
      if (nextStatus.status !== 'running') {
        setRebuilding(false)
        setLoadingDocs(false)
        setDocuments(await listRagDocuments(workspaceId))
      }
    } catch (err) {
      setRebuilding(false)
      setLoadingDocs(false)
      message.error(`重建索引失败: ${String(err)}`)
    }
  }

  async function upload(file: File) {
    if (!workspaceId) return
    uploadChainRef.current = uploadChainRef.current.then(async () => {
      setUploading(true)
      try {
        const payload = await uploadRagDocument(workspaceId, file)
        setDocuments(payload.documents)
        setRebuildStatus(payload.task)
        setRebuilding(true)
        message.success(`${file.name} 已接收，正在更新索引`)
      } catch (err) {
        message.error(`上传文档失败: ${String(err)}`)
      } finally {
        setUploading(false)
      }
    })
    await uploadChainRef.current
  }

  async function remove(documentId: string) {
    if (!workspaceId) return
    try {
      const payload = await deleteRagDocument(workspaceId, documentId)
      setDocuments(payload.documents)
      setRebuildStatus(payload.task)
      setRebuilding(true)
      message.success('删除任务已提交')
    } catch (err) {
      message.error(`删除文档失败: ${String(err)}`)
    }
  }

  async function search() {
    const value = query.trim()
    if (!value || !workspaceId) return
    setLoadingSearch(true)
    try {
      const payload = await searchRag(workspaceId, value)
      setResults(payload.results)
    } catch (err) {
      message.error(`检索失败: ${String(err)}`)
    } finally {
      setLoadingSearch(false)
    }
  }

  return (
    <Drawer
      title="RAG 调试"
      open={open}
      onClose={onClose}
      afterOpenChange={(visible) => {
        if (visible && workspaceId) {
          void loadDocuments()
        }
      }}
      width={560}
      className="rag-debug-drawer"
    >
      <section className="rag-debug-section">
        <div className="rag-debug-header">
          <Text strong>文档索引</Text>
          <Space>
            <Upload
              multiple
              showUploadList={false}
              accept=".md,.txt,.doc,.docx,.pdf"
              beforeUpload={(file) => {
                void upload(file)
                return false
              }}
            >
              <Button size="small" icon={<UploadOutlined />} loading={uploading} disabled={rebuilding}>
                上传
              </Button>
            </Upload>
            <Button size="small" icon={<ReloadOutlined />} loading={rebuilding} disabled={loadingDocs && !rebuilding} onClick={rebuild}>
              重建
            </Button>
          </Space>
        </div>
        {rebuildStatus && (
          <Alert
            type={rebuildAlertType(rebuildStatus)}
            showIcon
            className="rag-rebuild-status"
            message={rebuildStatus?.message || '正在重建 RAG 索引'}
            description={
              <div className="rag-rebuild-body">
                <Text type="secondary">
                  {rebuildProgressText(rebuildStatus, documents.length)}
                </Text>
                <Progress percent={rebuildStatus.percent} status={rebuildProgressStatus(rebuildStatus)} />
              </div>
            }
          />
        )}
        {!workspaceId ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请先选择工作区" />
        ) : documents.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无文档" />
        ) : (
          <List
            size="small"
            dataSource={documents}
            renderItem={(doc) => (
              <List.Item>
                <Space direction="vertical" size={2} className="rag-doc-item">
                  <Space>
                    <Text strong>{doc.source}</Text>
                    <Tag color={documentStatusColor(doc.status, doc.indexed)}>
                      {documentStatusLabel(doc.status, doc.indexed)}
                    </Tag>
                  </Space>
                  <Text type="secondary">{doc.characters} 字符 · {doc.chunks} chunks</Text>
                  {doc.error && <Text type="danger">{doc.error}</Text>}
                  {doc.preview_url && (
                    <a href={doc.preview_url} target="_blank" rel="noreferrer" className="rag-doc-link">
                      在浏览器中查看
                    </a>
                  )}
                </Space>
                <Popconfirm
                  title="删除文档"
                  description="删除后会在后台移除文件和索引，确认继续吗？"
                  okText="删除"
                  cancelText="取消"
                  disabled={rebuilding || doc.status === 'deleting'}
                  onConfirm={() => remove(doc.id)}
                >
                  <Button danger type="text" size="small" icon={<DeleteOutlined />} disabled={rebuilding || doc.status === 'deleting'} />
                </Popconfirm>
              </List.Item>
            )}
          />
        )}
      </section>

      <section className="rag-debug-section">
        <Text strong>检索调试</Text>
        <Space.Compact className="rag-search-box">
          <Input
            value={query}
            placeholder="输入要调试的 RAG 查询"
            onChange={(event) => setQuery(event.target.value)}
            onPressEnter={search}
          />
          <Button type="primary" icon={<SearchOutlined />} loading={loadingSearch} onClick={search}>
            检索
          </Button>
        </Space.Compact>

        <div className="rag-result-list">
          {results.map((item) => (
            <article key={item.citation} className="rag-result-card">
              <div className="rag-result-meta">
                <div className="rag-result-headline">
                  <Text strong>{item.citation}</Text>
                  {item.preview_url && (
                    <a href={item.preview_url} target="_blank" rel="noreferrer" className="rag-doc-link">
                      打开文档
                    </a>
                  )}
                </div>
                <Text type="secondary">
                  dense {item.dense_score.toFixed(3)} · sparse {item.sparse_score.toFixed(3)} · fused {item.fused_score.toFixed(3)}
                </Text>
              </div>
              {item.heading && <Text type="secondary">{item.heading}</Text>}
              <p>{item.text}</p>
            </article>
          ))}
        </div>
      </section>
    </Drawer>
  )
}

function rebuildProgressText(status: RagRebuildStatus | null, fallbackDocuments: number): string {
  if (!status) {
    return `准备中 · 当前工作区 ${fallbackDocuments} 个文档。`
  }
  const total = status.total || status.total_documents || fallbackDocuments
  const current = status.total ? status.current : 0
  const parts = [
    `阶段 ${status.stage}`,
    status.mode,
    `已用 ${status.elapsed_seconds}s`,
    total ? `进度 ${current}/${total}` : `文档 ${fallbackDocuments}`,
  ]
  parts.push(`已完成 ${status.processed}`)
  if (status.failed) parts.push(`失败 ${status.failed}`)
  if (status.total_chunks) parts.push(`${status.total_chunks} chunks`)
  if (status.current_document) parts.push(status.current_document)
  return parts.join(' · ')
}

function rebuildAlertType(status: RagRebuildStatus): 'success' | 'info' | 'error' {
  if (status.status === 'complete') return 'success'
  if (status.status === 'error') return 'error'
  return 'info'
}

function rebuildProgressStatus(status: RagRebuildStatus): 'success' | 'active' | 'exception' {
  if (status.status === 'complete') return 'success'
  if (status.status === 'error') return 'exception'
  return 'active'
}

function documentStatusLabel(status: string | undefined, indexed: boolean): string {
  if (status === 'deleting') return '删除中'
  if (status === 'processing') return '处理中'
  if (status === 'queued' || status === 'uploaded') return '排队中'
  if (status === 'error') return '失败'
  return indexed || status === 'indexed' ? '已索引' : '待处理'
}

function documentStatusColor(status: string | undefined, indexed: boolean): string {
  if (status === 'deleting') return 'purple'
  if (status === 'error') return 'red'
  if (status === 'processing') return 'blue'
  if (status === 'queued' || status === 'uploaded') return 'orange'
  return indexed || status === 'indexed' ? 'green' : 'default'
}

export default RagDebugPanel
