import React, { useMemo, useState } from 'react'
import { Button, Checkbox, Empty, Grid, Input, Popconfirm, Select, Space, Table, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, DownloadOutlined, EyeOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import type { WorkspaceDocument } from '@/api/localFeatures'

const { Text } = Typography

type StatusFilter = 'all' | 'indexed' | 'pending' | 'error'
type SortMode = 'updated_desc' | 'name_asc' | 'size_desc' | 'chunks_desc' | 'status'

interface KnowledgeDocumentTableProps {
  documents: WorkspaceDocument[]
  loading: boolean
  rebuilding: boolean
  selectedIds: string[]
  onSelectedIdsChange: (ids: string[]) => void
  onDelete: (documentId: string) => void
  onDeleteMany: (documentIds: string[]) => void
  onRefresh: () => void
}

const KnowledgeDocumentTable: React.FC<KnowledgeDocumentTableProps> = ({
  documents,
  loading,
  rebuilding,
  selectedIds,
  onSelectedIdsChange,
  onDelete,
  onDeleteMany,
  onRefresh,
}) => {
  const screens = Grid.useBreakpoint()
  const mobile = !screens.md
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [sortMode, setSortMode] = useState<SortMode>('updated_desc')
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(8)

  const visibleDocuments = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    return documents
      .filter((doc) => {
        const matchesQuery = !keyword || `${doc.filename} ${doc.content_hash ?? ''}`.toLowerCase().includes(keyword)
        const status = normalizedStatus(doc)
        const matchesStatus = statusFilter === 'all' || status === statusFilter
        return matchesQuery && matchesStatus
      })
      .sort((left, right) => compareDocuments(left, right, sortMode))
  }, [documents, query, sortMode, statusFilter])

  const maxPage = Math.max(1, Math.ceil(visibleDocuments.length / pageSize))
  const safeCurrentPage = Math.min(currentPage, maxPage)

  const columns: ColumnsType<WorkspaceDocument> = [
    {
      title: '文件',
      dataIndex: 'filename',
      width: mobile ? 240 : 380,
      render: (_value, doc) => (
        <Space direction="vertical" size={2} className="doc-name-cell">
          <Text strong ellipsis={{ tooltip: doc.filename }}>{doc.filename}</Text>
          <Text type="secondary">
            {doc.content_hash ? `sha256 ${doc.content_hash.slice(0, 10)}` : '未记录指纹'}
          </Text>
          {doc.error && <Text type="danger">{doc.error}</Text>}
        </Space>
      ),
    },
    {
      title: '状态',
      width: mobile ? 136 : 170,
      render: (_value, doc) => (
        <Space direction="vertical" size={4} className="doc-status-cell">
          <Tag color={documentStatusColor(doc.status, doc.indexed)}>
            {documentStatusLabel(doc.status, doc.indexed)}
          </Tag>
          {doc.index_version && <Text type="secondary" className="doc-status-meta">index {doc.index_version}</Text>}
        </Space>
      ),
    },
    {
      title: '规模',
      width: mobile ? 148 : 190,
      render: (_value, doc) => (
        <Space direction="vertical" size={2} className="doc-metrics-cell">
          <Text>{formatBytes(doc.size)}</Text>
          <Text type="secondary">{doc.characters.toLocaleString()} 字符</Text>
          <Text type="secondary">{doc.chunks} chunks</Text>
        </Space>
      ),
    },
    {
      title: '时间',
      width: mobile ? 148 : 200,
      render: (_value, doc) => (
        <Space direction="vertical" size={2} className="doc-time-cell">
          <Text>{formatDate(doc.updated_at)}</Text>
          <Text type="secondary">{formatClock(doc.updated_at)}</Text>
          <Text type="secondary">创建 {formatDate(doc.created_at)} {formatClock(doc.created_at)}</Text>
        </Space>
      ),
    },
    {
      title: '操作',
      width: mobile ? 132 : 148,
      fixed: mobile ? undefined : 'right',
      render: (_value, doc) => (
        <Space size={4}>
          <Tooltip title="预览">
            <Button
              size="small"
              type="text"
              icon={<EyeOutlined />}
              href={doc.preview_url}
              target="_blank"
              disabled={!doc.preview_url}
            />
          </Tooltip>
          <Tooltip title="下载">
            <Button
              size="small"
              type="text"
              icon={<DownloadOutlined />}
              href={doc.download_url}
              target="_blank"
              disabled={!doc.download_url}
            />
          </Tooltip>
          <Popconfirm
            title="删除文档"
            description="删除后会从知识库和索引中移除，确认继续吗？"
            okText="删除"
            cancelText="取消"
            disabled={rebuilding || doc.status === 'deleting'}
            onConfirm={() => onDelete(doc.id)}
          >
            <Tooltip title={rebuilding ? '索引任务运行中' : doc.status === 'deleting' ? '删除中' : '删除'}>
              <Button danger size="small" type="text" icon={<DeleteOutlined />} disabled={rebuilding || doc.status === 'deleting'} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="knowledge-doc-manager">
      <div className="knowledge-doc-tools">
        <Input
          allowClear
          prefix={<SearchOutlined />}
          value={query}
          placeholder="按文件名或指纹搜索"
          onChange={(event) => {
            setQuery(event.target.value)
            setCurrentPage(1)
          }}
        />
        <Select
          value={statusFilter}
          onChange={(value) => {
            setStatusFilter(value)
            setCurrentPage(1)
          }}
          options={[
            { value: 'all', label: '全部状态' },
            { value: 'indexed', label: '已索引' },
            { value: 'pending', label: '待处理' },
            { value: 'error', label: '失败' },
          ]}
        />
        <Select
          value={sortMode}
          onChange={(value) => {
            setSortMode(value)
            setCurrentPage(1)
          }}
          options={[
            { value: 'updated_desc', label: '最近更新' },
            { value: 'name_asc', label: '文件名 A-Z' },
            { value: 'size_desc', label: '文件大小' },
            { value: 'chunks_desc', label: '片段数量' },
            { value: 'status', label: '状态优先' },
          ]}
        />
        <Button icon={<ReloadOutlined />} onClick={onRefresh} loading={loading}>
          刷新
        </Button>
        <Popconfirm
          title="批量删除文档"
          description={`将删除选中的 ${selectedIds.length} 个文档，确认继续吗？`}
          okText="删除"
          cancelText="取消"
          disabled={selectedIds.length === 0 || rebuilding}
          onConfirm={() => onDeleteMany(selectedIds)}
        >
          <Button danger disabled={selectedIds.length === 0 || rebuilding}>
            删除选中
          </Button>
        </Popconfirm>
      </div>
      <div className="knowledge-doc-selection">
        <Text type="secondary">
          共 {documents.length} 个文档，当前显示 {visibleDocuments.length} 个，已选择 {selectedIds.length} 个
        </Text>
      </div>
      {mobile ? (
        renderMobileDocuments()
      ) : (
        <Table
          className="knowledge-doc-table"
          rowKey="id"
          size="middle"
          loading={loading}
          columns={columns}
          dataSource={visibleDocuments}
          tableLayout="fixed"
          pagination={{
            current: safeCurrentPage,
            pageSize,
            showSizeChanger: true,
            pageSizeOptions: ['8', '20', '50', '100'],
            showTotal: (total) => `共 ${total} 条`,
            onChange: (page, nextPageSize) => {
              setCurrentPage(page)
              if (nextPageSize && nextPageSize !== pageSize) {
                setPageSize(nextPageSize)
              }
            },
          }}
          rowSelection={{
            selectedRowKeys: selectedIds,
            onChange: (keys) => onSelectedIdsChange(keys.map(String)),
          }}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无文档" /> }}
          scroll={{ x: 1040 }}
        />
      )}
    </div>
  )

  function renderMobileDocuments() {
    const pageStart = (safeCurrentPage - 1) * pageSize
    const pageRows = visibleDocuments.slice(pageStart, pageStart + pageSize)
    if (!pageRows.length) {
      return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无文档" />
    }
    return (
      <div className="knowledge-doc-mobile-list">
        {pageRows.map((doc) => {
          const checked = selectedIds.includes(doc.id)
          return (
            <article key={doc.id} className="knowledge-doc-mobile-card">
              <div className="knowledge-doc-mobile-head">
                <Checkbox
                  checked={checked}
                  onChange={(event) => {
                    const next = event.target.checked
                      ? [...selectedIds, doc.id]
                      : selectedIds.filter((item) => item !== doc.id)
                    onSelectedIdsChange(Array.from(new Set(next)))
                  }}
                />
                <div className="knowledge-doc-mobile-title">
                  <Text strong>{doc.filename}</Text>
                  <Text type="secondary">{doc.content_hash ? `sha256 ${doc.content_hash.slice(0, 10)}` : '未记录指纹'}</Text>
                </div>
              </div>
              <div className="knowledge-doc-mobile-meta">
                <Tag color={documentStatusColor(doc.status, doc.indexed)}>{documentStatusLabel(doc.status, doc.indexed)}</Tag>
                {doc.index_version && <Text type="secondary">index {doc.index_version}</Text>}
                <Text type="secondary">{formatBytes(doc.size)}</Text>
                <Text type="secondary">{doc.characters.toLocaleString()} 字符 · {doc.chunks} chunks</Text>
                <Text type="secondary">更新 {formatDate(doc.updated_at)} {formatClock(doc.updated_at)}</Text>
                <Text type="secondary">创建 {formatDate(doc.created_at)} {formatClock(doc.created_at)}</Text>
                {doc.error && <Text type="danger">{doc.error}</Text>}
              </div>
              <div className="knowledge-doc-mobile-actions">
                <Button size="small" icon={<EyeOutlined />} href={doc.preview_url} target="_blank" disabled={!doc.preview_url}>
                  预览
                </Button>
                <Button size="small" icon={<DownloadOutlined />} href={doc.download_url} target="_blank" disabled={!doc.download_url}>
                  下载
                </Button>
                <Popconfirm
                  title="删除文档"
                  description="删除后会从知识库和索引中移除，确认继续吗？"
                  okText="删除"
                  cancelText="取消"
                  disabled={rebuilding || doc.status === 'deleting'}
                  onConfirm={() => onDelete(doc.id)}
                >
                  <Button size="small" danger disabled={rebuilding || doc.status === 'deleting'}>
                    删除
                  </Button>
                </Popconfirm>
              </div>
            </article>
          )
        })}
        <div className="knowledge-doc-mobile-pagination">
          <Text type="secondary">第 {safeCurrentPage} / {maxPage} 页</Text>
          <Space size={8}>
            <Button size="small" disabled={safeCurrentPage <= 1} onClick={() => setCurrentPage((value) => Math.max(1, value - 1))}>
              上一页
            </Button>
            <Button
              size="small"
              disabled={safeCurrentPage >= maxPage}
              onClick={() => setCurrentPage((value) => Math.min(maxPage, value + 1))}
            >
              下一页
            </Button>
          </Space>
        </div>
      </div>
    )
  }
}

function normalizedStatus(doc: WorkspaceDocument): StatusFilter {
  if (doc.status === 'error') return 'error'
  if (doc.indexed || doc.status === 'indexed' || doc.status === 'ready') return 'indexed'
  return 'pending'
}

function compareDocuments(left: WorkspaceDocument, right: WorkspaceDocument, sortMode: SortMode): number {
  if (sortMode === 'name_asc') return left.filename.localeCompare(right.filename)
  if (sortMode === 'size_desc') return (right.size || 0) - (left.size || 0)
  if (sortMode === 'chunks_desc') return (right.chunks || 0) - (left.chunks || 0)
  if (sortMode === 'status') return normalizedStatus(left).localeCompare(normalizedStatus(right))
  return timestamp(right.updated_at) - timestamp(left.updated_at)
}

function timestamp(value?: string): number {
  return value ? new Date(value).getTime() || 0 : 0
}

function formatDate(value?: string): string {
  if (!value) return '-'
  const [date] = value.split('T')
  return date || '-'
}

function formatClock(value?: string): string {
  if (!value) return '-'
  const [, time] = value.split('T')
  return time || '-'
}

function formatBytes(value: number | undefined): string {
  const size = Number(value || 0)
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
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

export default KnowledgeDocumentTable
