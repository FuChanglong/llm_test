import type { ChatMessage } from './chat'
export interface SessionSummary {
    id: string
    workspace_id: string
    title: string
    updated_at: string
}

export interface SessionDetail {
    id: string
    workspace_id: string
    title: string
    summary: string
    messages: ChatMessage[]
    updated_at: string
}
