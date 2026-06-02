import React, { useMemo, useState } from 'react'
import { Button, Card, Drawer, Empty, Input, Segmented, Space, Typography, Upload, message } from 'antd'
import { CopyOutlined, DownloadOutlined, EditOutlined, EyeOutlined, PictureOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons'
import { getErrorMessage } from '@/api/errors'
import { analyzeImage, editImage, generateImage } from '@/api/localFeatures'
import type { ImageAnalysisResponse, ImageResponse } from '@/api/localFeatures'

interface ImageStudioDrawerProps {
  open: boolean
  onClose: () => void
}

const promptPresets = [
  '做一张像 ChatGPT 官网宣传图一样克制、干净、带空间感的产品插画',
  '把这张图改成更适合产品官网 Hero 区的横版视觉',
  '分析这张截图的布局层级、视觉问题和可优化点',
]

const ImageStudioDrawer: React.FC<ImageStudioDrawerProps> = ({ open, onClose }) => {
  const [mode, setMode] = useState<'generate' | 'edit' | 'analyze'>('generate')
  const [prompt, setPrompt] = useState('')
  const [size, setSize] = useState('1024x1024')
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ImageResponse | null>(null)
  const [analysis, setAnalysis] = useState<ImageAnalysisResponse | null>(null)
  const [history, setHistory] = useState<Array<{ mode: string; prompt: string; result?: ImageResponse; analysis?: ImageAnalysisResponse }>>([])

  const currentPromptPlaceholder = useMemo(
    () => (mode === 'analyze' ? '描述你想让全模态模型分析什么' : mode === 'edit' ? '描述如何修改图片' : '描述要生成的图片'),
    [mode],
  )

  async function submit() {
    const value = prompt.trim()
    if (!value) return
    setLoading(true)
    try {
      if (mode === 'analyze') {
        if (!file) {
          message.error('请先上传一张图片')
          return
        }
        const next = await analyzeImage(value, file)
        setAnalysis(next)
        setResult(null)
        setHistory((current) => [{ mode, prompt: value, analysis: next }, ...current].slice(0, 8))
      } else if (mode === 'edit') {
        if (!file) {
          message.error('请先上传一张图片')
          return
        }
        const next = await editImage(value, file, size)
        setResult(next)
        setAnalysis(null)
        setHistory((current) => [{ mode, prompt: value, result: next }, ...current].slice(0, 8))
      } else {
        const next = await generateImage(value, size)
        setResult(next)
        setAnalysis(null)
        setHistory((current) => [{ mode, prompt: value, result: next }, ...current].slice(0, 8))
      }
    } catch (err) {
      message.error(`图片请求失败: ${getErrorMessage(err)}`)
    } finally {
      setLoading(false)
    }
  }

  async function downloadImage(src: string, index: number) {
    try {
      const response = await fetch(src)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = buildImageFilename(result?.model, index, blob.type)
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      message.error(`下载图片失败: ${getErrorMessage(err)}`)
    }
  }

  async function copyPrompt() {
    try {
      await navigator.clipboard.writeText(prompt)
      message.success('提示词已复制')
    } catch {
      message.error('复制提示词失败')
    }
  }

  return (
    <Drawer title="Image Studio" open={open} onClose={onClose} width={780} className="workspace-surface-drawer">
      <div className="image-studio">
        <Segmented
          value={mode}
          onChange={(value) => setMode(value as 'generate' | 'edit' | 'analyze')}
          options={[
            { label: '生成', value: 'generate', icon: <PictureOutlined /> },
            { label: '编辑', value: 'edit', icon: <EditOutlined /> },
            { label: '分析', value: 'analyze', icon: <EyeOutlined /> },
          ]}
        />
        <Space wrap>
          {promptPresets.map((item) => (
            <Button key={item} size="small" onClick={() => setPrompt(item)}>{item}</Button>
          ))}
        </Space>
        <Input.TextArea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          autoSize={{ minRows: 3, maxRows: 8 }}
          placeholder={currentPromptPlaceholder}
        />
        <Space wrap>
          {mode !== 'analyze' && (
            <Segmented
              value={size}
              onChange={(value) => setSize(String(value))}
              options={['1024x1024', '1536x1024', '1024x1536']}
            />
          )}
          {mode !== 'generate' && (
            <>
              <Upload
                showUploadList={false}
                beforeUpload={(nextFile) => {
                  setFile(nextFile)
                  return false
                }}
                accept=".png,.jpg,.jpeg,.webp"
              >
                <Button icon={<UploadOutlined />}>上传图片</Button>
              </Upload>
              {file ? <span>{file.name}</span> : null}
            </>
          )}
          <Button icon={<CopyOutlined />} onClick={() => void copyPrompt()}>
            复制提示词
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => { setResult(null); setAnalysis(null) }}>
            清空结果
          </Button>
          <Button type="primary" loading={loading} onClick={submit}>
            {mode === 'analyze' ? '开始分析' : mode === 'edit' ? '开始编辑' : '开始生成'}
          </Button>
        </Space>

        {analysis ? (
          <Card className="image-analysis-output" title={`分析结果 · ${analysis.model}`}>
            <Typography.Paragraph>{analysis.answer || '未返回分析内容'}</Typography.Paragraph>
          </Card>
        ) : result?.images?.length ? (
          <div className="image-grid">
            {result.images.map((item, index) => (
              <figure key={`${item.kind}-${index}`} className="image-card">
                <img src={item.data_url || item.url} alt={result.prompt} />
                <div className="image-card-actions">
                  <Button
                    icon={<DownloadOutlined />}
                    onClick={() => {
                      const src = item.data_url || item.url
                      if (!src) {
                        message.error('当前图片缺少可下载地址')
                        return
                      }
                      void downloadImage(src, index)
                    }}
                  >
                    下载
                  </Button>
                </div>
              </figure>
            ))}
          </div>
        ) : (
          <Empty description="暂无图片结果" />
        )}

        {history.length > 0 && (
          <Card className="image-history-card" title="最近任务">
            <Space direction="vertical" className="overview-full">
              {history.map((item, index) => (
                <button
                  key={`${item.mode}-${index}-${item.prompt}`}
                  type="button"
                  className="prompt-card"
                  onClick={() => {
                    setMode(item.mode as 'generate' | 'edit' | 'analyze')
                    setPrompt(item.prompt)
                    setResult(item.result || null)
                    setAnalysis(item.analysis || null)
                  }}
                >
                  <strong>{item.mode}</strong>
                  <span>{item.prompt}</span>
                </button>
              ))}
            </Space>
          </Card>
        )}
      </div>
    </Drawer>
  )
}

function buildImageFilename(model: string | undefined, index: number, mimeType: string) {
  const extension = mimeType.includes('png') ? 'png' : mimeType.includes('webp') ? 'webp' : mimeType.includes('jpeg') ? 'jpg' : 'png'
  const modelName = (model || 'image').replace(/[^a-zA-Z0-9_-]+/g, '_')
  return `${modelName}-${index + 1}.${extension}`
}

export default ImageStudioDrawer
