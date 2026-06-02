import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Empty, Progress, Space, Statistic, Tag, Typography, message } from 'antd'
import { CheckCircleOutlined, CopyOutlined, DatabaseOutlined, FileDoneOutlined, MessageOutlined, ReloadOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { getWorkspaceOverview } from '@/api/localFeatures'
import type { WorkspaceOverview } from '@/api/localFeatures'

const { Text, Title } = Typography

interface WorkspaceOverviewPageProps {
  workspaceId: string | null
  onOpenChat: () => void
  onOpenKnowledge: () => void
}

const WorkspaceOverviewPage: React.FC<WorkspaceOverviewPageProps> = ({ workspaceId, onOpenChat, onOpenKnowledge }) => {
  const [overview, setOverview] = useState<WorkspaceOverview | null>(null)
  const [loading, setLoading] = useState(false)

  const loadOverview = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      setOverview(await getWorkspaceOverview(workspaceId))
    } catch (err) {
      message.error(`加载工作区总览失败: ${String(err)}`)
    } finally {
      setLoading(false)
    }
  }, [workspaceId])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadOverview()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadOverview])

  useEffect(() => {
    const running = overview?.rebuild.status === 'running' || overview?.rebuild.status === 'queued'
    if (!workspaceId || !running) return undefined
    const timer = window.setInterval(() => {
      void loadOverview()
    }, 1200)
    return () => window.clearInterval(timer)
  }, [workspaceId, overview?.rebuild.status, loadOverview])

  const readiness = useMemo(() => {
    if (!overview) return 0
    const checks = [
      overview.stats.sessions > 0,
      overview.stats.documents > 0,
      overview.stats.documents === 0 || overview.stats.indexed_documents > 0,
      overview.stats.failed_documents === 0,
      overview.environment.model_configured,
    ]
    return Math.round((checks.filter(Boolean).length / checks.length) * 100)
  }, [overview])

  const acceptanceScriptText = useMemo(() => {
    if (!overview) return ''
    return (overview.acceptance_script ?? [])
      .map((step) => `${step.title}\n操作：${step.instruction}\n预期：${step.expected}`)
      .join('\n\n')
  }, [overview])

  async function copyAcceptanceScript() {
    if (!acceptanceScriptText) return
    try {
      await navigator.clipboard.writeText(acceptanceScriptText)
      message.success('已复制验收脚本')
    } catch {
      message.error('复制验收脚本失败')
    }
  }

  const deliveryChecks = overview?.delivery_checks ?? []
  const acceptanceScript = overview?.acceptance_script ?? []

  if (!workspaceId) {
    return (
      <div className="overview-page">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请先选择工作区" />
      </div>
    )
  }

  return (
    <div className="overview-page">
      <section className="overview-hero">
        <div>
          <Title level={4} className="overview-title">交付总览</Title>
          <Text type="secondary">聚合工作区数据、索引状态和客户验收前的关键检查项。</Text>
        </div>
        <Space wrap>
          <Button icon={<MessageOutlined />} onClick={onOpenChat}>进入对话</Button>
          <Button icon={<DatabaseOutlined />} onClick={onOpenKnowledge}>管理知识库</Button>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void loadOverview()}>刷新</Button>
        </Space>
      </section>

      {overview ? (
        <>
          <section className="overview-grid">
            <Card className="overview-card">
              <Statistic title="交付就绪度" value={readiness} suffix="%" prefix={<SafetyCertificateOutlined />} />
              <Progress percent={readiness} status={readiness >= 80 ? 'success' : 'active'} />
            </Card>
            <Card className="overview-card">
              <Statistic title="会话" value={overview.stats.sessions} prefix={<MessageOutlined />} />
              <Text type="secondary">最近更新 {formatTime(overview.latest_activity.session_updated_at)}</Text>
            </Card>
            <Card className="overview-card">
              <Statistic title="知识库文档" value={overview.stats.documents} prefix={<DatabaseOutlined />} />
              <Text type="secondary">{overview.stats.indexed_documents} 已索引 · {overview.stats.pending_documents} 待处理</Text>
            </Card>
            <Card className="overview-card">
              <Statistic title="索引片段" value={overview.stats.total_chunks} prefix={<FileDoneOutlined />} />
              <Text type="secondary">{overview.stats.total_characters.toLocaleString()} 字符 · {overview.stats.failed_documents} 失败</Text>
            </Card>
          </section>

          <section className="overview-two-column">
            <Card className="overview-card" title="运行状态">
              <Space direction="vertical" size={12} className="overview-full">
                <Alert
                  showIcon
                  type={overview.rebuild.status === 'error' ? 'error' : overview.rebuild.status === 'complete' ? 'success' : 'info'}
                  message={overview.rebuild.message}
                  description={`索引状态：${overview.rebuild.status} · 阶段：${overview.rebuild.stage}`}
                />
                <Progress percent={overview.rebuild.percent} status={overview.rebuild.status === 'error' ? 'exception' : overview.rebuild.status === 'complete' ? 'success' : 'active'} />
                <div className="overview-status-row">
                  <span>模型</span>
                  <Tag color={overview.environment.model_configured ? 'green' : 'orange'}>
                    {overview.environment.model_configured ? overview.environment.model : '待配置'}
                  </Tag>
                </div>
                <div className="overview-status-row">
                  <span>向量引擎</span>
                  <Tag>{overview.environment.embedder}</Tag>
                </div>
                <div className="overview-status-row">
                  <span>长期记忆</span>
                  <Tag color={overview.stats.enabled_memories > 0 ? 'green' : 'default'}>
                    {overview.stats.enabled_memories}/{overview.stats.memories}
                  </Tag>
                </div>
              </Space>
            </Card>

            <Card className="overview-card" title="下一步建议">
              <div className="overview-action-list">
                {overview.recommended_actions.map((action) => (
                  <article key={action.key} className="overview-action">
                    <Tag color={priorityColor(action.priority)}>{priorityLabel(action.priority)}</Tag>
                    <div>
                      <strong>{action.title}</strong>
                      <p>{action.description}</p>
                    </div>
                  </article>
                ))}
              </div>
            </Card>
          </section>

          <section className="overview-two-column">
            <Card className="overview-card" title="交付检查">
              <div className="overview-check-list">
                {deliveryChecks.length > 0 ? deliveryChecks.map((check) => (
                  <article key={check.key} className="overview-check-item">
                    <div className="overview-check-header">
                      <strong>{check.label}</strong>
                      <Tag color={deliveryCheckColor(check.status)}>{deliveryCheckLabel(check.status)}</Tag>
                    </div>
                    <p>{check.detail}</p>
                  </article>
                )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前后端尚未返回交付检查项" />}
              </div>
            </Card>

            <Card
              className="overview-card"
              title="客户验收脚本"
              extra={
                <Button type="text" icon={<CopyOutlined />} onClick={() => void copyAcceptanceScript()}>
                  复制
                </Button>
              }
            >
              <div className="acceptance-script-list">
                {acceptanceScript.length > 0 ? acceptanceScript.map((step) => (
                  <article key={step.key} className="acceptance-script-item">
                    <div className="acceptance-script-title">
                      <CheckCircleOutlined />
                      <strong>{step.title}</strong>
                    </div>
                    <p>操作：{step.instruction}</p>
                    <p>预期：{step.expected}</p>
                  </article>
                )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前后端尚未返回验收脚本" />}
              </div>
            </Card>
          </section>

          <Card className="overview-card" title="功能清单">
            <div className="capability-grid">
              {overview.capabilities.map((capability) => (
                <article key={capability.key} className="capability-tile">
                  <div className="capability-title">
                    <strong>{capability.label}</strong>
                    <Tag color={capabilityColor(capability.status)}>{capabilityStatusLabel(capability.status)}</Tag>
                  </div>
                  <p>{capability.description}</p>
                </article>
              ))}
            </div>
          </Card>
        </>
      ) : (
        <Card className="overview-card" loading={loading}>
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无总览数据" />
        </Card>
      )}
    </div>
  )
}

function formatTime(value: string | null): string {
  if (!value) return '暂无'
  return value.replace('T', ' ')
}

function priorityColor(priority: string): string {
  if (priority === 'high') return 'red'
  if (priority === 'medium') return 'orange'
  return 'blue'
}

function priorityLabel(priority: string): string {
  if (priority === 'high') return '高'
  if (priority === 'medium') return '中'
  return '低'
}

function capabilityColor(status: string): string {
  if (status === 'ready') return 'green'
  if (status === 'running') return 'blue'
  if (status === 'attention') return 'red'
  if (status === 'needs_setup') return 'orange'
  return 'default'
}

function capabilityStatusLabel(status: string): string {
  if (status === 'ready') return '可用'
  if (status === 'running') return '处理中'
  if (status === 'attention') return '需处理'
  if (status === 'needs_setup') return '待配置'
  return '可启用'
}

function deliveryCheckColor(status: string): string {
  if (status === 'pass') return 'green'
  if (status === 'warn') return 'orange'
  return 'red'
}

function deliveryCheckLabel(status: string): string {
  if (status === 'pass') return '通过'
  if (status === 'warn') return '关注'
  return '阻塞'
}

export default WorkspaceOverviewPage
