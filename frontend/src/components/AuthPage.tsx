import React from 'react'
import { Alert, Button, Card, Divider, Input, Progress, Segmented, Space, Typography } from 'antd'
import { ApiOutlined, DatabaseOutlined, LockOutlined, MailOutlined, SafetyCertificateOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons'
import { getPasswordScore, validateAuthForm } from '@/features/auth/authValidation'

const { Text, Title } = Typography

interface AuthPageProps {
  mode: 'login' | 'register'
  username: string
  email: string
  password: string
  displayName: string
  confirmPassword: string
  submitting: boolean
  errorMessage: string | null
  onModeChange: (mode: 'login' | 'register') => void
  onUsernameChange: (value: string) => void
  onEmailChange: (value: string) => void
  onPasswordChange: (value: string) => void
  onDisplayNameChange: (value: string) => void
  onConfirmPasswordChange: (value: string) => void
  onSubmit: () => void
}

interface WorkspaceAccessPageProps {
  userName: string
  workspaceDraft: string
  inviteDraft: string
  onWorkspaceDraftChange: (value: string) => void
  onInviteDraftChange: (value: string) => void
  onCreateWorkspace: () => void
  onJoinWorkspace: () => void
}

export const AuthPage: React.FC<AuthPageProps> = ({
  mode,
  username,
  email,
  password,
  displayName,
  confirmPassword,
  submitting,
  errorMessage,
  onModeChange,
  onUsernameChange,
  onEmailChange,
  onPasswordChange,
  onDisplayNameChange,
  onConfirmPasswordChange,
  onSubmit,
}) => {
  const passwordScore = getPasswordScore(password)
  const validation = validateAuthForm(mode, username, password, email, displayName, confirmPassword)
  return (
    <div className="auth-shell">
      <div className="auth-backdrop" aria-hidden="true" />
      <Card className="auth-card auth-card-wide">
        <section className="auth-panel">
          <div className="auth-brand">
            <span className="auth-brand-mark"><DatabaseOutlined /></span>
            <span>知识库问答工作台</span>
          </div>
          <div className="auth-copy">
            <div className="welcome-kicker">Private AI Workspace</div>
            <Title level={2}>{mode === 'login' ? '进入你的智能工作台' : '创建协作知识工作台'}</Title>
            <Text type="secondary">像 ChatGPT 一样快速开始，同时保留工作区、知识库、附件和长期记忆这些真正落地的能力。</Text>
          </div>
          <div className="auth-feature-list">
            <article>
              <SafetyCertificateOutlined />
              <span>Cookie 会话隔离，工作区权限校验</span>
            </article>
            <article>
              <TeamOutlined />
              <span>支持邀请码加入团队工作区</span>
            </article>
            <article>
              <MailOutlined />
              <span>邮箱注册，兼容用户名登录</span>
            </article>
          </div>
          <div className="auth-live-strip">
            <span><ApiOutlined /> API</span>
            <strong>已接入本地后端</strong>
          </div>
        </section>

        <section className="auth-form-panel">
          <Segmented
            block
            value={mode}
            onChange={(value) => onModeChange(value as 'login' | 'register')}
            options={[
              { label: '登录', value: 'login' },
              { label: '注册', value: 'register' },
            ]}
          />
          <Space direction="vertical" size={12} className="auth-form">
            {mode === 'register' && (
              <>
                <Input
                  prefix={<UserOutlined />}
                  value={displayName}
                  onChange={(event) => onDisplayNameChange(event.target.value)}
                  placeholder="显示名称"
                />
                <Input
                  prefix={<MailOutlined />}
                  value={email}
                  onChange={(event) => onEmailChange(event.target.value)}
                  placeholder="邮箱"
                  type="email"
                />
              </>
            )}
            <Input
              prefix={<UserOutlined />}
              value={username}
              onChange={(event) => onUsernameChange(event.target.value)}
              placeholder={mode === 'login' ? '用户名或邮箱' : '用户名'}
              onPressEnter={onSubmit}
            />
            <Input.Password
              prefix={<LockOutlined />}
              value={password}
              onChange={(event) => onPasswordChange(event.target.value)}
              placeholder="密码"
              onPressEnter={onSubmit}
            />
            {mode === 'register' && (
              <Input.Password
                prefix={<LockOutlined />}
                value={confirmPassword}
                onChange={(event) => onConfirmPasswordChange(event.target.value)}
                placeholder="再次输入密码"
                onPressEnter={onSubmit}
              />
            )}
            {mode === 'register' && password && (
              <div className="auth-password-meter">
                <Progress percent={passwordScore.percent} showInfo={false} size="small" strokeColor={passwordScore.color} />
                <Text type="secondary">{passwordScore.label}</Text>
              </div>
            )}
            {(errorMessage || validation.error) && (
              <Alert type="warning" showIcon message={errorMessage || validation.error} />
            )}
            <Button type="primary" block onClick={onSubmit} loading={submitting} disabled={!validation.canSubmit}>
              {mode === 'login' ? '登录' : '创建账户'}
            </Button>
            <Text type="secondary" className="auth-footnote">
              {mode === 'login' ? '可使用用户名或邮箱登录。' : '注册后会自动创建默认工作区，并可继续加入团队工作区。'}
            </Text>
          </Space>
        </section>
      </Card>
    </div>
  )
}

export const WorkspaceAccessPage: React.FC<WorkspaceAccessPageProps> = ({
  userName,
  workspaceDraft,
  inviteDraft,
  onWorkspaceDraftChange,
  onInviteDraftChange,
  onCreateWorkspace,
  onJoinWorkspace,
}) => {
  return (
    <div className="auth-shell">
      <div className="auth-backdrop" aria-hidden="true" />
      <Card className="auth-card workspace-access-card">
        <Title level={3}>选择团队工作区</Title>
        <Text type="secondary">{userName}，创建一个新工作区，或使用邀请码加入已有团队。</Text>
        <Divider />
        <Space direction="vertical" size={14} className="auth-form">
          <div className="workspace-inline-form">
            <Input
              value={workspaceDraft}
              onChange={(event) => onWorkspaceDraftChange(event.target.value)}
              placeholder="新工作区名称"
              onPressEnter={onCreateWorkspace}
            />
            <Button type="primary" onClick={onCreateWorkspace}>
              创建
            </Button>
          </div>
          <div className="workspace-inline-form">
            <Input
              value={inviteDraft}
              onChange={(event) => onInviteDraftChange(event.target.value)}
              placeholder="输入团队邀请码"
              onPressEnter={onJoinWorkspace}
            />
            <Button icon={<TeamOutlined />} onClick={onJoinWorkspace}>
              加入
            </Button>
          </div>
        </Space>
      </Card>
    </div>
  )
}
