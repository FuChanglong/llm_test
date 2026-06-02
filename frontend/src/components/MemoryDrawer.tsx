import React, { useEffect, useMemo, useState } from 'react'
import { Button, Drawer, Empty, Input, List, Segmented, Space, Switch, Typography, message } from 'antd'
import { CopyOutlined, DeleteOutlined, EditOutlined, PlusOutlined, SaveOutlined } from '@ant-design/icons'
import { getErrorMessage } from '@/api/errors'
import { createMemory, deleteMemory, listMemories, updateMemory } from '@/api/localFeatures'
import type { MemoryItem } from '@/api/localFeatures'

interface MemoryDrawerProps {
  open: boolean
  onClose: () => void
}

type FilterMode = 'all' | 'enabled' | 'disabled'

const MemoryDrawer: React.FC<MemoryDrawerProps> = ({ open, onClose }) => {
  const [items, setItems] = useState<MemoryItem[]>([])
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState('')
  const [filterMode, setFilterMode] = useState<FilterMode>('all')
  const [loading, setLoading] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')

  useEffect(() => {
    if (open) void refresh()
  }, [open])

  const visibleItems = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    return items.filter((item) => {
      const matchesQuery = !keyword || item.content.toLowerCase().includes(keyword)
      const matchesFilter = filterMode === 'all' || (filterMode === 'enabled' ? item.enabled : !item.enabled)
      return matchesQuery && matchesFilter
    })
  }, [filterMode, items, query])

  async function refresh() {
    setLoading(true)
    try {
      setItems(await listMemories())
    } catch (err) {
      message.error(`加载记忆失败: ${getErrorMessage(err)}`)
    } finally {
      setLoading(false)
    }
  }

  async function addMemory() {
    const content = draft.trim()
    if (!content) return
    try {
      await createMemory(content)
      setDraft('')
      await refresh()
    } catch (err) {
      message.error(`保存记忆失败: ${getErrorMessage(err)}`)
    }
  }

  async function toggleMemory(item: MemoryItem, enabled: boolean) {
    try {
      await updateMemory(item.id, { enabled })
      await refresh()
    } catch (err) {
      message.error(`更新记忆失败: ${getErrorMessage(err)}`)
    }
  }

  async function saveEdit(item: MemoryItem) {
    const content = editDraft.trim()
    if (!content) {
      message.warning('记忆内容不能为空')
      return
    }
    try {
      await updateMemory(item.id, { content })
      setEditingId(null)
      setEditDraft('')
      await refresh()
    } catch (err) {
      message.error(`更新记忆失败: ${getErrorMessage(err)}`)
    }
  }

  async function removeMemory(item: MemoryItem) {
    try {
      await deleteMemory(item.id)
      await refresh()
    } catch (err) {
      message.error(`删除记忆失败: ${getErrorMessage(err)}`)
    }
  }

  async function copyMemory(content: string) {
    try {
      await navigator.clipboard.writeText(content)
      message.success('记忆内容已复制')
    } catch {
      message.error('复制记忆失败')
    }
  }

  const enabledCount = items.filter((item) => item.enabled).length

  return (
    <Drawer title="本地 Memory" open={open} onClose={onClose} width={520} className="workspace-surface-drawer">
      <Space.Compact className="memory-input">
        <Input
          value={draft}
          placeholder="写入一条长期偏好或背景信息"
          onChange={(event) => setDraft(event.target.value)}
          onPressEnter={addMemory}
        />
        <Button type="primary" icon={<PlusOutlined />} onClick={addMemory}>
          添加
        </Button>
      </Space.Compact>
      <div className="memory-toolbar">
        <Input allowClear value={query} placeholder="搜索记忆内容" onChange={(event) => setQuery(event.target.value)} />
        <Segmented
          value={filterMode}
          onChange={(value) => setFilterMode(value as FilterMode)}
          options={[
            { value: 'all', label: `全部 ${items.length}` },
            { value: 'enabled', label: `启用 ${enabledCount}` },
            { value: 'disabled', label: `停用 ${items.length - enabledCount}` },
          ]}
        />
      </div>
      {visibleItems.length === 0 ? (
        <Empty description={items.length === 0 ? '暂无本地记忆' : '没有匹配的记忆'} />
      ) : (
        <List
          loading={loading}
          dataSource={visibleItems}
          renderItem={(item) => {
            const isEditing = editingId === item.id
            return (
              <List.Item
                actions={[
                  <Switch
                    key="switch"
                    checked={item.enabled}
                    size="small"
                    onChange={(checked) => toggleMemory(item, checked)}
                  />,
                  <Button key="copy" type="text" size="small" icon={<CopyOutlined />} onClick={() => void copyMemory(item.content)} />,
                  isEditing ? (
                    <Button key="save" type="text" size="small" icon={<SaveOutlined />} onClick={() => void saveEdit(item)} />
                  ) : (
                    <Button
                      key="edit"
                      type="text"
                      size="small"
                      icon={<EditOutlined />}
                      onClick={() => {
                        setEditingId(item.id)
                        setEditDraft(item.content)
                      }}
                    />
                  ),
                  <Button
                    key="delete"
                    type="text"
                    danger
                    size="small"
                    icon={<DeleteOutlined />}
                    onClick={() => void removeMemory(item)}
                  />,
                ]}
              >
                <Space direction="vertical" size={4} className="memory-item-content">
                  {isEditing ? (
                    <Input.TextArea value={editDraft} autoSize={{ minRows: 2, maxRows: 6 }} onChange={(event) => setEditDraft(event.target.value)} />
                  ) : (
                    <Typography.Text>{item.content}</Typography.Text>
                  )}
                  <Typography.Text type="secondary">
                    {item.enabled ? '已启用' : '已停用'} · 更新于 {new Date(item.updated_at).toLocaleString('zh-CN')}
                  </Typography.Text>
                </Space>
              </List.Item>
            )
          }}
        />
      )}
    </Drawer>
  )
}

export default MemoryDrawer
