import type { ChatMessage, ReasoningStep } from '@/api/chat'

export function latestAssistantReasoning(messages: ChatMessage[]): ReasoningStep[] {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
        const item = messages[index]
        if (item.role === 'assistant') return item.reasoning ?? []
    }
    return []
}

export function attachReasoningToLatestAssistant(messages: ChatMessage[], reasoning: ReasoningStep[]): ChatMessage[] {
    if (reasoning.length === 0) return messages
    const nextMessages = [...messages]
    for (let index = nextMessages.length - 1; index >= 0; index -= 1) {
        const item = nextMessages[index]
        if (item.role !== 'assistant') continue
        nextMessages[index] = { ...item, reasoning, status: 'done' }
        break
    }
    return nextMessages
}

export function markLatestAssistantStopped(messages: ChatMessage[]): ChatMessage[] {
    const nextMessages = [...messages]
    for (let index = nextMessages.length - 1; index >= 0; index -= 1) {
        const item = nextMessages[index]
        if (item.role !== 'assistant') continue
        nextMessages[index] = { ...item, content: item.content || '已停止生成。', status: 'done' }
        break
    }
    return nextMessages
}

export function appendAssistantReasoning(messages: ChatMessage[], step: ReasoningStep): ChatMessage[] {
    const nextMessages = [...messages]
    for (let index = nextMessages.length - 1; index >= 0; index -= 1) {
        const item = nextMessages[index]
        if (item.role !== 'assistant') continue
        nextMessages[index] = { ...item, reasoning: [...(item.reasoning ?? []), step], status: item.status ?? 'streaming' }
        return nextMessages
    }
    return messages
}

export function downloadText(content: string, filename: string) {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename.replace(/[\\/:*?"<>|]/g, '_')
    link.click()
    URL.revokeObjectURL(url)
}
