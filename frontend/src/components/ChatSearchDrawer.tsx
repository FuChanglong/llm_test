import React, { useMemo, useState } from 'react'
import { Button, Drawer, Empty, Input, List, Typography } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import type { SessionSummary } from '@/api/session'

interface ChatSearchDrawerProps {
  open: boolean
  sessions: SessionSummary[]
  currentSessionId: string | null
  onClose: () => void
  onSelectSession: (sessionId: string) => void
}

const ChatSearchDrawer: React.FC<ChatSearchDrawerProps> = ({
  open,
  sessions,
  currentSessionId,
  onClose,
  onSelectSession,
}) => {
  const [query, setQuery] = useState('')
  const visibleSessions = useMemo(() => {
    const value = query.trim().toLowerCase()
    if (!value) return sessions
    return sessions.filter((session) => session.title.toLowerCase().includes(value))
  }, [query, sessions])

  return (
    <Drawer
      title="搜索聊天"
      open={open}
      onClose={onClose}
      width={460}
      className="workspace-surface-drawer"
      afterOpenChange={(visible) => {
        if (!visible) setQuery('')
      }}
    >
      <div className="chat-search-panel">
        <Input
          autoFocus
          allowClear
          prefix={<SearchOutlined />}
          value={query}
          placeholder="搜索会话标题"
          onChange={(event) => setQuery(event.target.value)}
        />
        {visibleSessions.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={query ? '没有匹配的聊天' : '暂无聊天'} />
        ) : (
          <List
            dataSource={visibleSessions}
            renderItem={(session) => (
              <List.Item
                className={session.id === currentSessionId ? 'chat-search-item active' : 'chat-search-item'}
                actions={[
                  <Button
                    key="open"
                    size="small"
                    type={session.id === currentSessionId ? 'primary' : 'default'}
                    onClick={() => {
                      onSelectSession(session.id)
                      onClose()
                    }}
                  >
                    打开
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={session.title}
                  description={<Typography.Text type="secondary">{formatSessionTime(session.updated_at)}</Typography.Text>}
                />
              </List.Item>
            )}
          />
        )}
      </div>
    </Drawer>
  )
}

function formatSessionTime(value: string) {
  if (!value) return '暂无更新时间'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export default ChatSearchDrawer
