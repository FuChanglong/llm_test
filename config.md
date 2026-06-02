# 配置管理文档

本文档详细说明项目中所有可用的环境变量配置项。

## 核心配置

### LLM 配置
- `VLLM_BASE_URL` - LLM 服务的基础 URL，默认值：`https://dashscope.aliyuncs.com/compatible-mode/v1`
- `VLLM_API_KEY` - LLM 服务的 API 密钥，默认值：`EMPTY`
- `VLLM_MODEL` - 使用的 LLM 模型，默认值：`qwen3.6-plus`
- `VLLM_TIMEOUT_SECONDS` - LLM 请求超时时间（秒），默认值：`120`
- `VLLM_TRUST_ENV` - 是否信任环境变量中的代理设置，默认值：`0`

### MCP 服务器配置
- `MCP_HOST` - MCP 服务器主机，默认值：`127.0.0.1`
- `MCP_PORT` - MCP 服务器端口，默认值：`8765`
- `MCP_TRANSPORT` - MCP 传输协议，可选值：`stdio`, `sse`, `streamable-http`，默认值：`stdio`
- `MCP_SERVER_URL` - MCP 服务器 URL，默认值：空（使用 stdio 模式）
- `MCP_QUIET` - 是否静默运行 MCP 服务器，默认值：`0`

### Workspace RAG 配置
- `EMBEDDER_TYPE` - 嵌入器类型，可选值：`hash`, `huggingface`，默认值：`hash`

### 插件配置
- `PLUGINS_DIR` - 插件目录，默认值：`plugins`

### LangChain 文档配置
- `LANGCHAIN_DOCS_MCP_URL` - LangChain 文档 MCP 服务器 URL，默认值：`https://docs.langchain.com/mcp`

## 使用方法

1. 复制 `.env.example` 文件为 `.env`
2. 根据需要修改 `.env` 文件中的配置项
3. 启动服务时，系统会自动加载 `.env` 文件中的配置

## 示例配置

```dotenv
# LLM 配置
VLLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
VLLM_API_KEY=your_api_key_here
VLLM_MODEL=qwen3.6-plus
VLLM_TIMEOUT_SECONDS=120
VLLM_TRUST_ENV=0

# MCP 服务器配置
MCP_HOST=127.0.0.1
MCP_PORT=8765
MCP_TRANSPORT=streamable-http

# Workspace RAG 配置
EMBEDDER_TYPE=hash

# 插件配置
PLUGINS_DIR=plugins

# LangChain 文档配置
LANGCHAIN_DOCS_MCP_URL=https://docs.langchain.com/mcp
```

## 注意事项

- 所有配置项都是可选的，系统会使用默认值
- 对于生产环境，建议设置 `MCP_TRANSPORT=streamable-http` 以获得更好的性能
- 如果使用 `huggingface` 嵌入器，需要安装 `transformers` 和 `torch` 依赖
- 如果需要使用网络搜索功能，需要安装 `duckduckgo-search` 依赖
