import React from 'react'
import { Button, Divider, Empty, Flex, Input, Popover, Select, Spin, Typography, message } from 'antd'
import {
  AppstoreOutlined,
  CodeSandboxOutlined,
  CopyOutlined,
  DatabaseOutlined,
  EditOutlined,
  FileSearchOutlined,
  FolderAddOutlined,
  LogoutOutlined,
  MoreOutlined,
  PlusOutlined,
  SearchOutlined,
  SettingOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons'
import SessionItem from './SessionItem'
import type { WorkspaceSummary } from '@/api/auth'
import type { SessionSummary } from '@/api/session'

const { Text, Title } = Typography
export type AppView = 'overview' | 'chat' | 'knowledge'

interface SidebarProps {
  activeView: AppView
  sessions: SessionSummary[]
  currentSessionId: string | null
  loading: boolean
  workspaceId: string | null
  workspaces: WorkspaceSummary[]
  userName: string
  workspaceDraft: string
  inviteDraft: string
  onChangeView: (view: AppView) => void
  onNewSession: () => void
  onOpenSearch: () => void
  onSelectSession: (sessionId: string) => void
  onDeleteSession: (sessionId: string) => void
  onChangeWorkspace: (workspaceId: string) => void
  onWorkspaceDraftChange: (value: string) => void
  onInviteDraftChange: (value: string) => void
  onCreateWorkspace: () => void
  onJoinWorkspace: () => void
  onOpenResearch: () => void
  onOpenImages: () => void
  onOpenCanvas: () => void
  onOpenMemory: () => void
  onOpenRagDebug: () => void
  onOpenSettings: () => void
  onLogout: () => void
}

const Sidebar: React.FC<SidebarProps> = ({
  activeView,
  sessions,
  currentSessionId,
  loading,
  workspaceId,
  workspaces,
  userName,
  workspaceDraft,
  inviteDraft,
  onChangeView,
  onNewSession,
  onOpenSearch,
  onSelectSession,
  onDeleteSession,
  onChangeWorkspace,
  onWorkspaceDraftChange,
  onInviteDraftChange,
  onCreateWorkspace,
  onJoinWorkspace,
  onOpenResearch,
  onOpenImages,
  onOpenCanvas,
  onOpenMemory,
  onOpenRagDebug,
  onOpenSettings,
  onLogout,
}) => {
  const currentWorkspace = workspaces.find((item) => item.id === workspaceId)

  async function copyInviteCode() {
    const inviteCode = currentWorkspace?.invite_code?.trim()
    if (!inviteCode) {
      message.error('当前没有可复制的邀请码')
      return
    }
    try {
      await navigator.clipboard.writeText(inviteCode)
      message.success('邀请码已复制')
    } catch {
      message.error('复制邀请码失败')
    }
  }

  function createSession() {
    onChangeView('chat')
    onNewSession()
  }

  const workspacePanel = (
    <div className="workspace-menu">
      <Text strong>工作区</Text>
      <Select
        value={workspaceId ?? undefined}
        options={workspaces.map((item) => ({ value: item.id, label: item.name }))}
        onChange={onChangeWorkspace}
      />
      <div className="workspace-menu-copy">
        <Input readOnly value={currentWorkspace?.invite_code || '暂无邀请码'} />
        <Button icon={<CopyOutlined />} onClick={() => void copyInviteCode()} />
      </div>
      <Divider />
      <div className="workspace-menu-copy">
        <Input
          value={workspaceDraft}
          placeholder="新工作区名称"
          onChange={(event) => onWorkspaceDraftChange(event.target.value)}
          onPressEnter={onCreateWorkspace}
        />
        <Button icon={<PlusOutlined />} onClick={onCreateWorkspace} />
      </div>
      <div className="workspace-menu-copy">
        <Input
          value={inviteDraft}
          placeholder="输入邀请码加入"
          onChange={(event) => onInviteDraftChange(event.target.value)}
          onPressEnter={onJoinWorkspace}
        />
        <Button icon={<TeamOutlined />} onClick={onJoinWorkspace} />
      </div>
    </div>
  )

  return (
    <Flex vertical className="sidebar-inner">
      <div className="sidebar-brand-row">
        <Popover trigger="click" placement="bottomLeft" content={workspacePanel}>
          <button type="button" className="workspace-switcher">
            <CodeSandboxOutlined />
            <span>{currentWorkspace?.name || '知识库问答'}</span>
          </button>
        </Popover>
        <Button type="text" icon={<MoreOutlined />} className="sidebar-icon-button" />
      </div>

      <nav className="global-nav" aria-label="主导航">
        <button type="button" className="global-nav-item primary" onClick={createSession}>
          <EditOutlined />
          <span>新聊天</span>
        </button>
        <button type="button" className="global-nav-item" onClick={onOpenSearch}>
          <SearchOutlined />
          <span>搜索聊天</span>
        </button>
        <button
          type="button"
          className={activeView === 'knowledge' ? 'global-nav-item active' : 'global-nav-item'}
          onClick={() => onChangeView('knowledge')}
        >
          <DatabaseOutlined />
          <span>知识库</span>
        </button>
        <button type="button" className="global-nav-item" onClick={onOpenResearch}>
          <FileSearchOutlined />
          <span>Research</span>
        </button>
        <button type="button" className="global-nav-item" onClick={onOpenImages}>
          <AppstoreOutlined />
          <span>应用 / 工具</span>
        </button>
      </nav>

      <section className="sidebar-section">
        <Title level={5} className="sidebar-section-title">项目</Title>
        <button
          type="button"
          className={activeView === 'overview' ? 'project-nav-item active' : 'project-nav-item'}
          onClick={() => onChangeView('overview')}
        >
          <FolderAddOutlined />
          <span>工作区主页</span>
        </button>
        <button
          type="button"
          className={activeView === 'chat' ? 'project-nav-item active' : 'project-nav-item'}
          onClick={() => onChangeView('chat')}
        >
          <CodeSandboxOutlined />
          <span>当前对话</span>
        </button>
      </section>

      <section className="sidebar-section session-section">
        <div className="sidebar-section-head">
          <Title level={5} className="sidebar-section-title">最近</Title>
          <Button type="text" size="small" icon={<PlusOutlined />} onClick={createSession} />
        </div>
        <Spin spinning={loading}>
          {sessions.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无会话" />
          ) : (
            <div className="session-list">
              {sessions.map((session) => (
                <SessionItem
                  key={session.id}
                  session={session}
                  isActive={currentSessionId === session.id}
                  onSelect={(sessionId) => { onChangeView('chat'); onSelectSession(sessionId) }}
                  onDelete={onDeleteSession}
                />
              ))}
            </div>
          )}
        </Spin>
      </section>

      <section className="sidebar-section tool-shortcuts">
        <Title level={5} className="sidebar-section-title">工具</Title>
        <button type="button" className="project-nav-item" onClick={onOpenCanvas}>Canvas</button>
        <button type="button" className="project-nav-item" onClick={onOpenMemory}>Memory</button>
        <button type="button" className="project-nav-item" onClick={onOpenRagDebug}>RAG 调试</button>
      </section>

      <div className="sidebar-user">
        <button type="button" className="sidebar-user-main" onClick={onOpenSettings}>
          <span className="sidebar-avatar"><UserOutlined /></span>
          <span>
            <strong>{userName}</strong>
            <Text type="secondary">设置与账户</Text>
          </span>
        </button>
        <Button type="text" icon={<SettingOutlined />} onClick={onOpenSettings} />
        <Button type="text" icon={<LogoutOutlined />} onClick={onLogout} />
      </div>
    </Flex>
  )
}

export default Sidebar
