import { useCallback, useEffect, useRef, useState } from 'react'
import type { MessageInstance } from 'antd/es/message/interface'
import type { ModalStaticFunctions } from 'antd/es/modal/confirm'

import api from '@/api/request'
import type { ChatAttachment, ChatMessage, ChatStreamEvent } from '@/api/chat'
import { streamChat, streamEditChat, streamRegenerateChat } from '@/api/chat'
import type { SessionDetail, SessionSummary } from '@/api/session'
import { createMemory, exportSession } from '@/api/localFeatures'
import {
    appendAssistantReasoning,
    attachReasoningToLatestAssistant,
    downloadText,
    latestAssistantReasoning,
    markLatestAssistantStopped,
} from './messageTransforms'

export type ChatMode = 'balanced' | 'fast' | 'research' | 'rag'
const CHAT_MODE_STORAGE_KEY = 'llm_test_chat_mode_v1'

export function useChatWorkspace(
    currentWorkspaceId: string | null,
    message: MessageInstance,
    modal: Omit<ModalStaticFunctions, 'warn'>,
    defaultChatMode: ChatMode,
) {
    const [sessions, setSessions] = useState<SessionSummary[]>([])
    const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
    const [currentSession, setCurrentSession] = useState<SessionDetail | null>(null)
    const [input, setInput] = useState('')
    const [loadingSessions, setLoadingSessions] = useState(false)
    const [loadingChat, setLoadingChat] = useState(false)
    const [pendingAttachments, setPendingAttachments] = useState<ChatAttachment[]>([])
    const [chatMode, setChatMode] = useState<ChatMode>(() => loadChatMode(defaultChatMode))
    const activeControllerRef = useRef<AbortController | null>(null)
    const messageRef = useRef(message)
    const currentWorkspaceRef = useRef<string | null>(currentWorkspaceId)
    const selectedSessionByWorkspaceRef = useRef<Record<string, string | null>>({})

    useEffect(() => {
        messageRef.current = message
    }, [message])

    useEffect(() => {
        window.localStorage.setItem(CHAT_MODE_STORAGE_KEY, chatMode)
    }, [chatMode])

    useEffect(() => {
        try {
            const savedMode = window.localStorage.getItem(CHAT_MODE_STORAGE_KEY)
            if (!savedMode) setChatMode(defaultChatMode)
        } catch {
            setChatMode(defaultChatMode)
        }
    }, [defaultChatMode])

    const fetchSessions = useCallback(async (workspaceId = currentWorkspaceId) => {
        if (!workspaceId) return
        setLoadingSessions(true)
        try {
            const res = await api.get<SessionSummary[]>(`/api/v1/workspaces/${workspaceId}/sessions`)
            const nextSessions = res.data
            const remembered = selectedSessionByWorkspaceRef.current[workspaceId]
            const fallbackId = nextSessions[0]?.id ?? null
            const nextSessionId = remembered && nextSessions.some((item) => item.id === remembered) ? remembered : fallbackId
            if (currentWorkspaceRef.current === workspaceId) {
                setSessions(nextSessions)
                setCurrentSessionId(nextSessionId)
            }
        } catch (err) {
            messageRef.current.error(`获取会话失败: ${String(err)}`)
        } finally {
            setLoadingSessions(false)
        }
    }, [currentWorkspaceId])

    const fetchSessionDetail = useCallback(async (workspaceId: string, sessionId: string) => {
        try {
            const res = await api.get<SessionDetail>(`/api/v1/workspaces/${workspaceId}/sessions/${sessionId}`)
            if (currentWorkspaceRef.current === workspaceId) {
                setCurrentSession(res.data)
            }
        } catch (err) {
            if (currentWorkspaceRef.current !== workspaceId) return
            setCurrentSession(null)
            if ((err as { response?: { status?: number } })?.response?.status === 404) {
                selectedSessionByWorkspaceRef.current[workspaceId] = null
                void fetchSessions(workspaceId)
                return
            }
            messageRef.current.error(`获取会话详情失败: ${String(err)}`)
        }
    }, [fetchSessions])

    useEffect(() => () => {
        activeControllerRef.current?.abort()
    }, [])

    useEffect(() => {
        currentWorkspaceRef.current = currentWorkspaceId
        activeControllerRef.current?.abort()
        setLoadingChat(false)
        setPendingAttachments([])
        setSessions([])
        setCurrentSessionId(null)
        setCurrentSession(null)
        if (currentWorkspaceId) {
            void fetchSessions(currentWorkspaceId)
        }
    }, [currentWorkspaceId, fetchSessions])

    useEffect(() => {
        activeControllerRef.current?.abort()
        setLoadingChat(false)
        setPendingAttachments([])
        if (currentWorkspaceId && currentSessionId) {
            selectedSessionByWorkspaceRef.current[currentWorkspaceId] = currentSessionId
            void fetchSessionDetail(currentWorkspaceId, currentSessionId)
        } else {
            setCurrentSession(null)
        }
    }, [currentWorkspaceId, currentSessionId, fetchSessionDetail])

    async function createSessionInWorkspace() {
        if (!currentWorkspaceId) return null
        try {
            const res = await api.post<SessionDetail>(`/api/v1/workspaces/${currentWorkspaceId}/sessions`, {})
            await fetchSessions()
            setCurrentSessionId(res.data.id)
            setCurrentSession(res.data)
            return res.data
        } catch (err) {
            message.error(`创建会话失败: ${String(err)}`)
            return null
        }
    }

    async function deleteSession(sessionId: string) {
        if (!currentWorkspaceId) return
        modal.confirm({
            title: '删除会话',
            content: '删除后不可恢复，确认继续吗？',
            okText: '删除',
            cancelText: '取消',
            okButtonProps: { danger: true },
            onOk: async () => {
                try {
                    await api.delete(`/api/v1/workspaces/${currentWorkspaceId}/sessions/${sessionId}`)
                    const nextSessions = sessions.filter((item) => item.id !== sessionId)
                    setSessions(nextSessions)
                    if (currentSessionId === sessionId) {
                        if (nextSessions.length > 0) {
                            setCurrentSessionId(nextSessions[0].id)
                        } else {
                            setCurrentSessionId(null)
                            setCurrentSession(null)
                        }
                    }
                } catch (err) {
                    message.error(`删除会话失败: ${String(err)}`)
                }
            },
        })
    }

    async function sendMessage() {
        const content = input.trim()
        if (!content || !currentWorkspaceId || loadingChat) return
        let targetSessionId = currentSessionId
        if (!targetSessionId) {
            const created = await createSessionInWorkspace()
            targetSessionId = created?.id ?? null
        }
        if (!targetSessionId) return
        const attachments = pendingAttachments
        setInput('')
        setPendingAttachments([])
        const userMessage: ChatMessage = { role: 'user', content, time: new Date().toISOString(), attachments }
        const assistantMessage: ChatMessage = { role: 'assistant', content: '', time: new Date().toISOString(), status: 'streaming', reasoning: [] }
        setCurrentSession((prev) => prev ? { ...prev, messages: [...prev.messages, userMessage, assistantMessage] } : {
            id: targetSessionId,
            workspace_id: currentWorkspaceId,
            title: '新会话',
            summary: '',
            messages: [userMessage, assistantMessage],
            updated_at: new Date().toISOString(),
        })
        await runStreamingRequest(
            targetSessionId,
            assistantMessage,
            (onEvent, signal) => streamChat(
                { session_id: targetSessionId, message: buildModeMessage(content, chatMode), attachment_ids: attachments.map((item) => item.id) },
                onEvent,
                signal,
            ),
            () => setPendingAttachments(attachments),
        )
    }

    async function editMessage(messageId: string, content: string) {
        if (!currentSessionId || !currentWorkspaceId || loadingChat) return
        const currentMessages = currentSession?.messages ?? []
        const messageIndex = currentMessages.findIndex((item) => item.id === messageId)
        const target = currentMessages[messageIndex]
        if (!target || target.role !== 'user') return
        const attachments = target.attachments ?? []
        const assistantMessage: ChatMessage = { role: 'assistant', content: '', time: new Date().toISOString(), status: 'streaming', reasoning: [] }
        setCurrentSession((prev) => {
            if (!prev) return prev
            const nextMessages = prev.messages.slice(0, messageIndex + 1)
            nextMessages[messageIndex] = { ...target, content, attachments }
            nextMessages.push(assistantMessage)
            return { ...prev, messages: nextMessages }
        })
        await runStreamingRequest(
            currentSessionId,
            assistantMessage,
            (onEvent, signal) => streamEditChat(
                { session_id: currentSessionId, message_id: messageId, message: content, attachment_ids: attachments.map((item) => item.id) },
                onEvent,
                signal,
            ),
        )
    }

    async function regenerateMessage(messageId: string) {
        if (!currentSessionId || loadingChat) return
        const currentMessages = currentSession?.messages ?? []
        const messageIndex = currentMessages.findIndex((item) => item.id === messageId)
        if (messageIndex < 0) return
        const assistantMessage: ChatMessage = { role: 'assistant', content: '', time: new Date().toISOString(), status: 'streaming', reasoning: [] }
        setCurrentSession((prev) => prev ? { ...prev, messages: [...prev.messages.slice(0, messageIndex), assistantMessage] } : prev)
        await runStreamingRequest(
            currentSessionId,
            assistantMessage,
            (onEvent, signal) => streamRegenerateChat({ session_id: currentSessionId, message_id: messageId }, onEvent, signal),
        )
    }

    async function runStreamingRequest(
        sessionId: string,
        assistantMessage: ChatMessage,
        request: (onEvent: (event: ChatStreamEvent) => void, signal: AbortSignal) => Promise<void>,
        onAbort?: () => void,
    ) {
        activeControllerRef.current?.abort()
        const controller = new AbortController()
        activeControllerRef.current = controller
        setLoadingChat(true)
        try {
            await request((event) => {
                if (event.type === 'start') return
                if (event.type === 'token') {
                    setCurrentSession((prev) => appendToken(prev, assistantMessage, event.content))
                    return
                }
                if (event.type === 'reasoning' || event.type === 'tool_start' || event.type === 'tool_end' || event.type === 'tool_error') {
                    setCurrentSession((prev) => prev && prev.id === sessionId ? { ...prev, messages: appendAssistantReasoning(prev.messages, event) } : prev)
                    return
                }
                if (event.type === 'error') throw new Error(event.message)
                setCurrentSession((prev) => {
                    if (!prev) return prev
                    const previousReasoning = latestAssistantReasoning(prev.messages)
                    return {
                        id: sessionId,
                        workspace_id: event.workspace_id,
                        title: event.title,
                        summary: event.summary,
                        messages: attachReasoningToLatestAssistant(event.messages, previousReasoning),
                        updated_at: event.updated_at,
                    }
                })
            }, controller.signal)
            await fetchSessions()
        } catch (err) {
            if (controller.signal.aborted) {
                onAbort?.()
                setCurrentSession((prev) => prev && prev.id === sessionId ? { ...prev, messages: markLatestAssistantStopped(prev.messages) } : prev)
                return
            }
            setCurrentSession((prev) => markLatestAssistantError(prev, String(err)))
            message.error(`发送消息失败: ${String(err)}`)
        } finally {
            if (activeControllerRef.current === controller) {
                activeControllerRef.current = null
                setLoadingChat(false)
            }
        }
    }

    function stopGeneration() {
        activeControllerRef.current?.abort()
        activeControllerRef.current = null
        setLoadingChat(false)
        if (currentSessionId) {
            setCurrentSession((prev) => prev && prev.id === currentSessionId ? { ...prev, messages: markLatestAssistantStopped(prev.messages) } : prev)
        }
    }

    async function saveAsMemory(content: string) {
        try {
            await createMemory(content.slice(0, 2000))
            message.success('已保存为本地记忆')
        } catch (err) {
            message.error(`保存记忆失败: ${String(err)}`)
        }
    }

    async function exportCurrentSession() {
        if (!currentWorkspaceId || !currentSessionId) return
        try {
            const data = await exportSession(currentWorkspaceId, currentSessionId)
            downloadText(data, `${currentSession?.title || currentSessionId}.json`)
        } catch (err) {
            message.error(`导出失败: ${String(err)}`)
        }
    }

    return {
        sessions,
        currentSessionId,
        currentSession,
        input,
        loadingSessions,
        loadingChat,
        pendingAttachments,
        chatMode,
        setCurrentSessionId,
        setInput,
        setPendingAttachments,
        setChatMode,
        createSessionInWorkspace,
        deleteSession,
        sendMessage,
        editMessage,
        regenerateMessage,
        stopGeneration,
        saveAsMemory,
        exportCurrentSession,
    }
}

function buildModeMessage(content: string, mode: ChatMode): string {
    if (mode === 'balanced') return content
    const modeInstruction: Record<Exclude<ChatMode, 'balanced'>, string> = {
        fast: '请优先给出简洁直接的答案，避免展开过长推理，必要时列出后续可深入的点。',
        research: '请用研究助理模式回答：先明确结论，再给出依据、假设、风险和下一步验证建议。',
        rag: '请优先使用工作区知识库、附件和可引用来源回答；如果证据不足，请明确说明缺口，不要编造引用。',
    }
    return `${modeInstruction[mode]}\n\n用户问题：${content}`
}

function loadChatMode(defaultChatMode: ChatMode): ChatMode {
    try {
        const value = window.localStorage.getItem(CHAT_MODE_STORAGE_KEY)
        return value === 'fast' || value === 'research' || value === 'rag' || value === 'balanced' ? value : defaultChatMode
    } catch {
        return defaultChatMode
    }
}

function appendToken(session: SessionDetail | null, assistantMessage: ChatMessage, content: string): SessionDetail | null {
    if (!session) return session
    const nextMessages = [...session.messages]
    const lastIndex = nextMessages.length - 1
    const lastMessage = nextMessages[lastIndex]
    if (!lastMessage || lastMessage.role !== 'assistant') {
        nextMessages.push({ ...assistantMessage, content })
    } else {
        nextMessages[lastIndex] = { ...lastMessage, content: lastMessage.content + content, status: 'streaming' }
    }
    return { ...session, messages: nextMessages }
}

function markLatestAssistantError(session: SessionDetail | null, error: string): SessionDetail | null {
    if (!session) return session
    const nextMessages = [...session.messages]
    const lastIndex = nextMessages.length - 1
    const lastMessage = nextMessages[lastIndex]
    const errorContent = `发送失败：${error}`
    if (lastMessage?.role === 'assistant') {
        nextMessages[lastIndex] = { ...lastMessage, content: lastMessage.content || errorContent, status: 'error' }
    } else {
        nextMessages.push({ role: 'assistant', content: errorContent, time: new Date().toISOString(), status: 'error' })
    }
    return { ...session, messages: nextMessages }
}
