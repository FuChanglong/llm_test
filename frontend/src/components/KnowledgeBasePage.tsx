import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Button, Card, Empty, Input, Progress, Space, Tag, Typography, Upload, message } from 'antd'
import { MessageOutlined, ReloadOutlined, SearchOutlined, UploadOutlined } from '@ant-design/icons'
import {
  deleteRagDocuments,
  getRagRebuildStatus,
  listRagDocuments,
  rebuildRagIndex,
  searchRag,
  uploadRagDocument,
} from '@/api/localFeatures'
import type { RagRebuildStatus, RagSearchResult, WorkspaceDocument } from '@/api/localFeatures'
import KnowledgeDocumentTable from './KnowledgeDocumentTable'

const { Text, Title } = Typography

interface KnowledgeBasePageProps {
  workspaceId: string | null
  onUseInChat?: (text: string) => void
}

const KnowledgeBasePage: React.FC<KnowledgeBasePageProps> = ({ workspaceId, onUseInChat }) => {
  const [documents, setDocuments] = useState<WorkspaceDocument[]>([])
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<RagSearchResult[]>([])
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [loadingSearch, setLoadingSearch] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [rebuildStatus, setRebuildStatus] = useState<RagRebuildStatus | null>(null)
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([])
  const uploadChainRef = useRef<Promise<void>>(Promise.resolve())
  const statusDismissTimerRef = useRef<number | null>(null)

  const documentStats = useMemo(() => buildDocumentStats(documents), [documents])
  const failedDocuments = useMemo(() => documents.filter((doc) => doc.status === 'error'), [documents])

  const loadDocuments = useCallback(async () => {
    if (!workspaceId) return
    setLoadingDocs(true)
    try {
      setDocuments(await listRagDocuments(workspaceId))
    } catch (err) {
      message.error(`加载知识库失败: ${String(err)}`)
    } finally {
      setLoadingDocs(false)
    }
  }, [workspaceId])

  const refreshStatus = useCallback(async () => {
    if (!workspaceId) return
    try {
      const nextStatus = await getRagRebuildStatus(workspaceId)
      setRebuildStatus(nextStatus)
      setRebuilding(nextStatus.status === 'running' || nextStatus.status === 'queued')
      if (nextStatus.status === 'complete' || nextStatus.status === 'error') {
        setDocuments(await listRagDocuments(workspaceId))
      }
    } catch (err) {
      setRebuilding(false)
      message.error(`获取索引状态失败: ${String(err)}`)
    }
  }, [workspaceId])

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
    if (!workspaceId) return
    const timer = window.setTimeout(() => {
      void loadDocuments()
      void refreshStatus()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [workspaceId, loadDocuments, refreshStatus])

  useEffect(() => {
    if (!rebuilding || !workspaceId) return undefined
    const timer = window.setInterval(() => {
      void refreshStatus()
    }, 1000)
    return () => window.clearInterval(timer)
  }, [rebuilding, workspaceId, refreshStatus])

  async function rebuild() {
    if (!workspaceId) return
    setRebuilding(true)
    try {
      const nextStatus = await rebuildRagIndex(workspaceId)
      setRebuildStatus(nextStatus)
      void refreshStatus()
      if (nextStatus.status !== 'running' && nextStatus.status !== 'queued') {
        setRebuilding(false)
        setDocuments(await listRagDocuments(workspaceId))
      }
    } catch (err) {
      setRebuilding(false)
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
        void refreshStatus()
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
    await removeMany([documentId])
  }

  async function removeMany(documentIds: string[]) {
    if (!workspaceId) return
    const ids = Array.from(new Set(documentIds)).filter(Boolean)
    if (ids.length === 0) return
    try {
      const payload = await deleteRagDocuments(workspaceId, ids)
      setDocuments(payload.documents)
      setRebuildStatus(payload.task)
      setRebuilding(true)
      void refreshStatus()
      setSelectedDocumentIds((prev) => prev.filter((id) => !ids.includes(id)))
      message.success(ids.length === 1 ? '删除任务已提交' : `已提交 ${ids.length} 个文档的删除任务`)
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
    <div className="knowledge-page">
      <section className="knowledge-main">
        <div className="knowledge-toolbar">
          <div>
            <Title level={4} className="knowledge-title">知识库</Title>
            <Text type="secondary">管理工作区文档、索引任务和检索质量。</Text>
          </div>
          <Space>
            <Upload
              multiple
              showUploadList={false}
              accept=".md,.txt,.doc,.docx,.pdf"
              disabled={!workspaceId || uploading || rebuilding}
              beforeUpload={(file) => {
                void upload(file)
                return false
              }}
            >
              <Button icon={<UploadOutlined />} loading={uploading} disabled={!workspaceId || rebuilding}>
                上传文档
              </Button>
            </Upload>
            <Button icon={<ReloadOutlined />} loading={rebuilding} disabled={!workspaceId || loadingDocs} onClick={rebuild}>
              重建索引
            </Button>
          </Space>
        </div>

        {rebuildStatus && rebuildStatus.status !== 'idle' && (
          <Alert
            showIcon
            className="knowledge-status"
            type={rebuildAlertType(rebuildStatus)}
            message={rebuildStatus.message}
            description={
              <div className="knowledge-status-body">
                <Text type="secondary">{rebuildProgressText(rebuildStatus)}</Text>
                <Progress percent={rebuildStatus.percent} status={rebuildProgressStatus(rebuildStatus)} />
              </div>
            }
          />
        )}

        <div className="knowledge-stats">
          <article>
            <span>文档总数</span>
            <strong>{documentStats.total}</strong>
          </article>
          <article>
            <span>已索引</span>
            <strong>{documentStats.indexed}</strong>
          </article>
          <article>
            <span>待处理</span>
            <strong>{documentStats.pending}</strong>
          </article>
          <article>
            <span>片段 / 容量</span>
            <strong>{documentStats.chunks} / {formatBytes(documentStats.size)}</strong>
          </article>
        </div>

        {failedDocuments.length > 0 && (
          <Card
            className="knowledge-card failed-doc-card"
            title={`失败文档 ${failedDocuments.length} 个`}
            extra={
              <Button
                danger
                disabled={rebuilding}
                onClick={() => { void removeMany(failedDocuments.map((doc) => doc.id)) }}
              >
                删除全部失败文档
              </Button>
            }
          >
            <div className="failed-doc-list">
              {failedDocuments.map((doc) => (
                <article key={doc.id} className="failed-doc-item">
                  <div>
                    <strong>{doc.filename}</strong>
                    <p>{doc.error || '未返回具体失败原因'}</p>
                  </div>
                  <Button
                    size="small"
                    danger
                    disabled={rebuilding}
                    onClick={() => { void remove(doc.id) }}
                  >
                    删除
                  </Button>
                </article>
              ))}
            </div>
          </Card>
        )}

        <Card className="knowledge-card" title="文件管理">
          {!workspaceId ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请先选择工作区" />
          ) : (
            <KnowledgeDocumentTable
              documents={documents}
              loading={loadingDocs}
              rebuilding={rebuilding}
              selectedIds={selectedDocumentIds}
              onSelectedIdsChange={setSelectedDocumentIds}
              onDelete={(documentId) => { void remove(documentId) }}
              onDeleteMany={(documentIds) => { void removeMany(documentIds) }}
              onRefresh={() => { void loadDocuments() }}
            />
          )}
        </Card>
      </section>

      <aside className="knowledge-side">
        <Card className="knowledge-card" title="检索测试">
          <Space.Compact className="knowledge-search">
            <Input value={query} placeholder="输入查询，查看命中文档" onChange={(event) => setQuery(event.target.value)} onPressEnter={search} />
            <Button type="primary" icon={<SearchOutlined />} loading={loadingSearch} onClick={search}>
              检索
            </Button>
          </Space.Compact>
          <div className="knowledge-results">
            {results.map((item) => (
              <article key={item.citation} className="knowledge-result">
                <div className="knowledge-result-head">
                  {item.preview_url ? (
                    <a href={item.preview_url} target="_blank" rel="noreferrer" className="source-link">
                      {item.title ?? item.source}
                    </a>
                  ) : (
                    <Text strong>{item.title ?? item.source}</Text>
                  )}
                  {item.citation && <Tag>{item.citation}</Tag>}
                </div>
                <p>{resultExcerpt(item)}</p>
                <div className="source-score-row">
                  <span>dense {scoreText(item.dense_score)}</span>
                  <span>sparse {scoreText(item.sparse_score)}</span>
                  <span>fused {scoreText(item.fused_score)}</span>
                  {item.rerank_score != null && <span>rerank {scoreText(item.rerank_score)}</span>}
                </div>
                <div className="knowledge-result-actions">
                  <Button
                    size="small"
                    icon={<MessageOutlined />}
                    disabled={!onUseInChat}
                    onClick={() => onUseInChat?.(buildEvidencePrompt(item))}
                  >
                    带证据提问
                  </Button>
                  {item.preview_url && (
                    <Button size="small" type="link" href={item.preview_url} target="_blank">
                      预览原文
                    </Button>
                  )}
                </div>
              </article>
            ))}
          </div>
        </Card>
      </aside>
    </div>
  )
}

function rebuildProgressText(status: RagRebuildStatus): string {
  const parts = [
    `阶段 ${status.stage}`,
    `进度 ${status.current}/${status.total || status.total_documents || 0}`,
    `已用 ${status.elapsed_seconds}s`,
  ]
  if (status.total_chunks) parts.push(`${status.total_chunks} chunks`)
  if (status.current_document) parts.push(status.current_document)
  if (status.failed) parts.push(`失败 ${status.failed}`)
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

function resultExcerpt(item: RagSearchResult): string {
  return item.snippet || item.collapsed_excerpt || item.text || '暂无可显示片段'
}

function scoreText(value: number | null | undefined): string {
  return typeof value === 'number' ? value.toFixed(3) : '-'
}

function buildEvidencePrompt(item: RagSearchResult): string {
  const title = item.title ?? item.source
  const citation = item.citation ? `\n引用：${item.citation}` : ''
  const excerpt = resultExcerpt(item).slice(0, 900)
  return `请基于以下知识库证据回答我的问题，并在回答中保留来源引用。\n\n来源：${title}${citation}\n\n证据片段：\n${excerpt}\n\n我的问题：`
}

function buildDocumentStats(documents: WorkspaceDocument[]) {
  return documents.reduce(
    (stats, doc) => {
      stats.total += 1
      stats.size += doc.size || 0
      stats.chunks += doc.chunks || 0
      if (doc.status === 'error') stats.failed += 1
      else if (doc.indexed || doc.status === 'indexed' || doc.status === 'ready') stats.indexed += 1
      else stats.pending += 1
      return stats
    },
    { total: 0, indexed: 0, pending: 0, failed: 0, chunks: 0, size: 0 },
  )
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

export default KnowledgeBasePage
