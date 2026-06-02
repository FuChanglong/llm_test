import React from 'react'
import { Button, Dropdown, Typography } from 'antd'
import { DatabaseOutlined, EllipsisOutlined, MenuOutlined, ShareAltOutlined } from '@ant-design/icons'
import type { WorkspaceSummary } from '@/api/auth'
import type { AppView } from './Sidebar'

const { Text, Title } = Typography

interface ChatHeaderProps {
  mobile: boolean
  activeView: AppView
  workspaceId: string | null
  workspaces: WorkspaceSummary[]
  onOpenSidebar: () => void
  onOpenSettings: () => void
  onOpenKnowledge: () => void
  onShare: () => void
  onExport?: () => void
}

const viewTitle: Record<AppView, string> = {
  overview: '工作区主页',
  chat: '当前对话',
  knowledge: '知识库',
}

const ChatHeader: React.FC<ChatHeaderProps> = ({
  mobile,
  activeView,
  workspaceId,
  workspaces,
  onOpenSidebar,
  onOpenSettings,
  onOpenKnowledge,
  onShare,
  onExport,
}) => {
  const currentWorkspace = workspaces.find((item) => item.id === workspaceId)
  return (
    <div className="header">
      <div className="header-main">
        {mobile && (
          <Button
            type="text"
            icon={<MenuOutlined />}
            className="header-menu-button"
            onClick={onOpenSidebar}
            aria-label="打开导航"
          />
        )}
        <div className="header-copy">
          <Title level={5} className="header-title">
            {activeView === 'chat' ? currentWorkspace?.name || '知识库问答' : viewTitle[activeView]}
          </Title>
          {!mobile && (
            <Text type="secondary" className="header-subtitle">
              {activeView === 'chat' ? viewTitle.chat : currentWorkspace?.name || '当前工作区'}
            </Text>
          )}
        </div>
      </div>
      <div className="header-ops">
        {!mobile && (
          <Button type="text" icon={<DatabaseOutlined />} onClick={onOpenKnowledge}>
            知识库
          </Button>
        )}
        <Button type="text" icon={<ShareAltOutlined />} onClick={onShare}>
          分享
        </Button>
        <Dropdown
          trigger={['click']}
          menu={{
            items: [
              { key: 'settings', label: '设置' },
              { key: 'knowledge', label: '打开知识库' },
              { key: 'export', label: '导出当前会话', disabled: !onExport },
            ],
            onClick: ({ key }) => {
              if (key === 'settings') onOpenSettings()
              if (key === 'knowledge') onOpenKnowledge()
              if (key === 'export') onExport?.()
            },
          }}
        >
          <Button type="text" icon={<EllipsisOutlined />} aria-label="更多" />
        </Dropdown>
      </div>
    </div>
  )
}

export default ChatHeader
