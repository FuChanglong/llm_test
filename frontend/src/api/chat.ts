import { buildApiUrl } from './request'

export interface ReasoningStep {
    type: 'reasoning' | 'tool_start' | 'tool_end' | 'tool_error'
    content?: string
    name?: string
    input?: string
    duration_ms?: number
}

export interface ChatMessage {
    id?: string
    role: 'user' | 'assistant'
    content: string
    time: string
    status?: 'streaming' | 'done' | 'error'
    reasoning?: ReasoningStep[]
    sources?: ChatSource[]
    attachments?: ChatAttachment[]
}

export interface ChatSource {
    kind?: 'rag' | 'attachment' | string
    source: string
    chunk_id?: number
    parent_id?: number
    heading?: string
    citation?: string
    dense_score?: number
    sparse_score?: number
    fused_score?: number
    rerank_score?: number | null
    text?: string
    snippet?: string
    document_id?: string
    preview_url?: string | null
    download_url?: string | null
    title?: string
    collapsed_excerpt?: string
}

export interface ChatAttachment {
    id: string
    session_id: string
    workspace_id?: string
    message_id?: string | null
    filename: string
    mime_type: string
    size: number
    status: 'ready' | 'error' | string
    error?: string | null
    created_at: string
    chunks: number
}

export interface ChatResponse {
    session_id: string
    workspace_id: string
    title: string
    summary: string
    reply: string
    messages: ChatMessage[]
    updated_at: string
}

export type ChatStreamEvent =
    | { type: 'start' }
    | { type: 'token'; content: string }
    | { type: 'reasoning'; content: string }
    | { type: 'tool_start'; name: string; input: string }
    | { type: 'tool_end'; name: string; duration_ms?: number }
    | { type: 'tool_error'; name: string }
    | { type: 'error'; message: string }
    | (ChatResponse & { type: 'done'; memory_compressed: boolean })

interface StreamChatPayload {
    session_id: string
    message: string
    attachment_ids?: string[]
}

interface StreamEditPayload extends StreamChatPayload {
    message_id: string
}

interface StreamRegeneratePayload {
    session_id: string
    message_id: string
}

export async function streamChat(
    payload: StreamChatPayload,
    onEvent: (event: ChatStreamEvent) => void,
    signal?: AbortSignal,
) {
    return streamChatEndpoint('/api/v1/chat/stream', payload, onEvent, signal)
}

export async function streamEditChat(
    payload: StreamEditPayload,
    onEvent: (event: ChatStreamEvent) => void,
    signal?: AbortSignal,
) {
    return streamChatEndpoint('/api/v1/chat/edit/stream', payload, onEvent, signal)
}

export async function streamRegenerateChat(
    payload: StreamRegeneratePayload,
    onEvent: (event: ChatStreamEvent) => void,
    signal?: AbortSignal,
) {
    return streamChatEndpoint('/api/v1/chat/regenerate/stream', payload, onEvent, signal)
}

async function streamChatEndpoint(
    endpoint: string,
    payload: StreamChatPayload | StreamEditPayload | StreamRegeneratePayload,
    onEvent: (event: ChatStreamEvent) => void,
    signal?: AbortSignal,
) {
    const response = await fetch(buildApiUrl(endpoint), {
        method: 'POST',
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
        signal,
    })

    if (!response.ok || !response.body) {
        const errorText = await response.text()
        throw new Error(errorText || `HTTP ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
        const { value, done } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
            if (!line.trim()) continue
            onEvent(parseChatStreamLine(line))
        }
    }

    buffer += decoder.decode()
    if (buffer.trim()) {
        onEvent(parseChatStreamLine(buffer))
    }
}

export function parseChatStreamLine(line: string): ChatStreamEvent {
    try {
        return JSON.parse(line) as ChatStreamEvent
    } catch {
        throw new Error(`Invalid chat stream event: ${line}`)
    }
}
