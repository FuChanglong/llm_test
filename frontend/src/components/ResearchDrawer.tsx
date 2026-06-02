import React, { useEffect, useMemo, useState } from 'react'
import { Button, Drawer, Empty, Input, InputNumber, List, Segmented, Space, Tabs, Typography, message } from 'antd'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { CopyOutlined, HistoryOutlined } from '@ant-design/icons'
import { getErrorMessage } from '@/api/errors'
import { deepResearch, webSearch } from '@/api/localFeatures'
import type { DeepResearchResponse, WebSearchResponse } from '@/api/localFeatures'

const { Text } = Typography
const HISTORY_KEY = 'llm_test_research_history_v1'

interface ResearchDrawerProps {
  open: boolean
  onClose: () => void
  onUseInChat: (text: string) => void
}

const ResearchDrawer: React.FC<ResearchDrawerProps> = ({ open, onClose, onUseInChat }) => {
  const [query, setQuery] = useState('')
  const [loadingSearch, setLoadingSearch] = useState(false)
  const [loadingDeep, setLoadingDeep] = useState(false)
  const [maxResults, setMaxResults] = useState(5)
  const [maxPages, setMaxPages] = useState(3)
  const [searchResult, setSearchResult] = useState<WebSearchResponse | null>(null)
  const [deepResult, setDeepResult] = useState<DeepResearchResponse | null>(null)
  const [history, setHistory] = useState<string[]>(() => loadResearchHistory())

  const trimmedQuery = query.trim()
  const hasResult = Boolean(searchResult?.results?.length || deepResult)
  const historyItems = useMemo(() => history.filter(Boolean).slice(0, 8), [history])

  useEffect(() => {
    try {
      window.localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, 12)))
    } catch {
      // ignore storage failure
    }
  }, [history])

  async function runSearch() {
    if (!trimmedQuery) return
    setLoadingSearch(true)
    try {
      const nextResult = await webSearch(trimmedQuery, maxResults)
      setSearchResult(nextResult)
      rememberHistory(trimmedQuery)
    } catch (err) {
      message.error(`联网搜索失败: ${getErrorMessage(err)}`)
    } finally {
      setLoadingSearch(false)
    }
  }

  async function runDeepResearch() {
    if (!trimmedQuery) return
    setLoadingDeep(true)
    try {
      const nextResult = await deepResearch(trimmedQuery, maxResults, maxPages)
      setDeepResult(nextResult)
      rememberHistory(trimmedQuery)
    } catch (err) {
      message.error(`Deep Research 失败: ${getErrorMessage(err)}`)
    } finally {
      setLoadingDeep(false)
    }
  }

  async function copySummary() {
    if (!deepResult?.summary) return
    try {
      await navigator.clipboard.writeText(deepResult.summary)
      message.success('研究摘要已复制')
    } catch {
      message.error('复制研究摘要失败')
    }
  }

  function rememberHistory(value: string) {
    setHistory((current) => [value, ...current.filter((item) => item !== value)].slice(0, 12))
  }

  return (
    <Drawer title="Research" open={open} onClose={onClose} width={760} className="workspace-surface-drawer">
      <Space direction="vertical" size={12} className="overview-full research-shell">
        <Space.Compact className="research-toolbar">
          <Input
            value={query}
            placeholder="输入联网搜索或 Deep Research 问题"
            onChange={(event) => setQuery(event.target.value)}
            onPressEnter={runSearch}
          />
          <Button loading={loadingSearch} onClick={runSearch}>
            联网搜索
          </Button>
          <Button type="primary" loading={loadingDeep} onClick={runDeepResearch}>
            Deep Research
          </Button>
        </Space.Compact>

        <Space wrap>
          <Text type="secondary">搜索结果数</Text>
          <InputNumber min={1} max={10} value={maxResults} onChange={(value) => setMaxResults(Number(value) || 5)} />
          <Text type="secondary">抓取网页数</Text>
          <InputNumber min={1} max={5} value={maxPages} onChange={(value) => setMaxPages(Number(value) || 3)} />
          <Segmented
            value={hasResult ? 'result' : 'history'}
            options={[
              { value: 'result', label: '结果' },
              { value: 'history', label: '历史' },
            ]}
            disabled={!historyItems.length && !hasResult}
          />
        </Space>

        {historyItems.length > 0 && (
          <div className="research-history-row">
            <Text type="secondary"><HistoryOutlined /> 最近问题</Text>
            <Space wrap>
              {historyItems.map((item) => (
                <Button key={item} size="small" onClick={() => setQuery(item)}>{item}</Button>
              ))}
            </Space>
          </div>
        )}

        <Tabs
          items={[
            {
              key: 'search',
              label: '搜索结果',
              children: searchResult?.results?.length ? (
                <List
                  dataSource={searchResult.results}
                  renderItem={(item) => (
                    <List.Item
                      actions={[
                        <Button
                          key="use"
                          size="small"
                          onClick={() => onUseInChat(`请基于这个网页继续分析：${item.title}\n${item.url}`)}
                        >
                          发到聊天
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={
                          <a href={item.url} target="_blank" rel="noreferrer">
                            {item.title}
                          </a>
                        }
                        description={
                          <Space direction="vertical" size={2}>
                            <Text type="secondary">{item.domain}</Text>
                            <Text>{item.snippet}</Text>
                          </Space>
                        }
                      />
                    </List.Item>
                  )}
                />
              ) : (
                <Empty description="暂无搜索结果" />
              ),
            },
            {
              key: 'deep',
              label: '研究摘要',
              children: deepResult ? (
                <div className="research-result">
                  <Space wrap className="research-actions">
                    <Button icon={<CopyOutlined />} onClick={() => void copySummary()}>复制摘要</Button>
                    <Button onClick={() => onUseInChat(`请继续基于这份研究摘要展开：\n\n${deepResult.summary}`)}>
                      发到聊天
                    </Button>
                  </Space>
                  <div className="markdown-body">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{deepResult.summary}</ReactMarkdown>
                  </div>
                  <List
                    header="引用网页"
                    dataSource={deepResult.sources}
                    renderItem={(item) => (
                      <List.Item>
                        <List.Item.Meta
                          title={
                            <a href={item.url} target="_blank" rel="noreferrer">
                              {item.title}
                            </a>
                          }
                          description={item.snippet}
                        />
                      </List.Item>
                    )}
                  />
                </div>
              ) : (
                <Empty description="暂无研究结果" />
              ),
            },
          ]}
        />
      </Space>
    </Drawer>
  )
}

function loadResearchHistory() {
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.map(String) : []
  } catch {
    return []
  }
}

export default ResearchDrawer
