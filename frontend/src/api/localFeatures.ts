import api, { buildApiUrl } from './request'
import type { ChatAttachment } from './chat'
import type { SessionDetail } from './session'

export interface MemoryItem {
    id: string
    content: string
    enabled: boolean
    created_at: string
    updated_at: string
}

export interface CanvasDoc {
    id: string
    session_id: string
    title: string
    content: string
    created_at: string
    updated_at: string
}

export interface TableAnalysis {
    filename: string
    rows: number
    columns: string[]
    column_types: Record<string, string>
    missing_values: Record<string, number>
    numeric_summary: Record<string, unknown>
    sample_rows: Record<string, unknown>[]
}

export interface WebSearchItem {
    title: string
    snippet: string
    url: string
    domain?: string
}

export interface WebSearchResponse {
    query: string
    results: WebSearchItem[]
}

export interface DeepResearchResponse {
    query: string
    summary: string
    sources: Array<WebSearchItem & { content: string }>
    search_results: WebSearchItem[]
}

export interface ImageResult {
    kind: 'base64' | 'url' | string
    data_url?: string
    url?: string
}

export interface ImageResponse {
    prompt: string
    model: string
    images: ImageResult[]
}

export interface ImageAnalysisResponse {
    prompt: string
    model: string
    filename: string
    answer: string
}

export interface SpeechSynthesisOptions {
    voice?: string
    rate?: number
}

export interface WorkspaceDocument {
    id: string
    source: string
    filename: string
    size: number
    status?: string
    index_status?: string
    index_version?: string
    error?: string | null
    indexed: boolean
    characters: number
    chunks: number
    content_hash?: string
    created_at?: string
    updated_at?: string
    preview_url?: string
    download_url?: string
}

export interface RagRebuildStatus {
    id: string | null
    workspace_id: string
    status: 'idle' | 'running' | 'complete' | 'error' | string
    stage: string
    message: string
    current: number
    total: number
    percent: number
    total_documents: number
    total_chunks: number
    current_document: string
    index_version?: string
    mode: string
    processed: number
    failed: number
    elapsed_seconds: number
    error?: string | null
}

export interface RagSearchResult {
    source: string
    chunk_id: number
    parent_id: number
    heading: string
    citation: string
    dense_score: number
    sparse_score: number
    fused_score: number
    rerank_score: number | null
    text: string
    snippet?: string
    preview_url?: string | null
    download_url?: string | null
    title?: string
    collapsed_excerpt?: string
}

export interface WorkspaceOverview {
    workspace_id: string
    stats: {
        sessions: number
        documents: number
        indexed_documents: number
        pending_documents: number
        failed_documents: number
        total_chunks: number
        total_characters: number
        memories: number
        enabled_memories: number
    }
    latest_activity: {
        session_updated_at: string | null
        index_updated_at: string | null
    }
    rebuild: RagRebuildStatus
    environment: {
        model: string
        model_configured: boolean
        embedder: string
    }
    capabilities: Array<{
        key: string
        label: string
        status: string
        description: string
    }>
    recommended_actions: Array<{
        key: string
        priority: 'high' | 'medium' | 'low' | string
        title: string
        description: string
    }>
    delivery_checks: Array<{
        key: string
        label: string
        status: 'pass' | 'warn' | 'fail' | string
        detail: string
    }>
    acceptance_script: Array<{
        key: string
        title: string
        instruction: string
        expected: string
    }>
}

export async function uploadSessionAttachment(workspaceId: string, sessionId: string, file: File) {
    const form = new FormData()
    form.append('file', file)
    const response = await api.post<ChatAttachment>(
        `/api/v1/workspaces/${workspaceId}/sessions/${sessionId}/attachments`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } },
    )
    return response.data
}

export async function deleteSessionAttachment(workspaceId: string, sessionId: string, attachmentId: string) {
    await api.delete(`/api/v1/workspaces/${workspaceId}/sessions/${sessionId}/attachments/${attachmentId}`)
}

export async function exportSession(workspaceId: string, sessionId: string) {
    const response = await fetch(
        buildApiUrl(`/api/v1/workspaces/${workspaceId}/sessions/${sessionId}/export?format=json`),
        { credentials: 'include' },
    )
    if (!response.ok) throw new Error(await response.text())
    return JSON.stringify((await response.json()) as SessionDetail, null, 2)
}

export async function listMemories() {
    const response = await api.get<MemoryItem[]>('/api/v1/memory')
    return response.data
}

export async function createMemory(content: string, enabled = true) {
    const response = await api.post<MemoryItem>('/api/v1/memory', { content, enabled })
    return response.data
}

export async function updateMemory(memoryId: string, payload: { content?: string; enabled?: boolean }) {
    const response = await api.patch<MemoryItem>(`/api/v1/memory/${memoryId}`, payload)
    return response.data
}

export async function deleteMemory(memoryId: string) {
    await api.delete(`/api/v1/memory/${memoryId}`)
}

export async function getCanvas(workspaceId: string, sessionId: string) {
    const response = await api.get<CanvasDoc>(`/api/v1/workspaces/${workspaceId}/sessions/${sessionId}/canvas`)
    return response.data
}

export async function updateCanvas(workspaceId: string, sessionId: string, payload: { title?: string; content?: string }) {
    const response = await api.put<CanvasDoc>(`/api/v1/workspaces/${workspaceId}/sessions/${sessionId}/canvas`, payload)
    return response.data
}

export async function transformCanvas(
    workspaceId: string,
    sessionId: string,
    payload: { content: string; instruction: string; mode: 'polish' | 'summarize' | 'rewrite' | 'expand' },
) {
    const response = await api.post<{ content: string }>(
        `/api/v1/workspaces/${workspaceId}/sessions/${sessionId}/canvas/transform`,
        payload,
    )
    return response.data.content
}

export async function analyzeAttachment(workspaceId: string, sessionId: string, attachmentId: string) {
    const response = await api.post<TableAnalysis>(`/api/v1/workspaces/${workspaceId}/sessions/${sessionId}/analysis`, {
        attachment_id: attachmentId,
    })
    return response.data
}

export async function listRagDocuments(workspaceId: string) {
    const response = await api.get<{ documents: WorkspaceDocument[] }>(`/api/v1/workspaces/${workspaceId}/rag/documents`)
    return response.data.documents
}

export async function rebuildRagIndex(workspaceId: string) {
    const response = await api.post<{ rebuild: RagRebuildStatus }>(`/api/v1/workspaces/${workspaceId}/rag/rebuild`)
    return response.data.rebuild
}

export async function getRagRebuildStatus(workspaceId: string) {
    const response = await api.get<{ rebuild: RagRebuildStatus }>(`/api/v1/workspaces/${workspaceId}/rag/rebuild/status`)
    return response.data.rebuild
}

export async function uploadRagDocument(workspaceId: string, file: File) {
    const form = new FormData()
    form.append('file', file)
    const response = await api.post<{ documents: WorkspaceDocument[]; task: RagRebuildStatus }>(
        `/api/v1/workspaces/${workspaceId}/rag/upload`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } },
    )
    return response.data
}

export async function deleteRagDocument(workspaceId: string, documentId: string) {
    return deleteRagDocuments(workspaceId, [documentId])
}

export async function deleteRagDocuments(workspaceId: string, documentIds: string[]) {
    const ids = Array.from(new Set(documentIds)).filter(Boolean)
    const response = await api.post<{ documents: WorkspaceDocument[]; task: RagRebuildStatus }>(
        `/api/v1/workspaces/${workspaceId}/rag/documents/delete`,
        { document_ids: ids },
    )
    return response.data
}

export async function searchRag(workspaceId: string, query: string, topK = 6) {
    const response = await api.post<{ query: string; index_version?: string; results: RagSearchResult[] }>(
        `/api/v1/workspaces/${workspaceId}/rag/search`,
        { query, top_k: topK },
    )
    return response.data
}

export async function getWorkspaceOverview(workspaceId: string) {
    const response = await api.get<WorkspaceOverview>(`/api/v1/workspaces/${workspaceId}/overview`)
    return response.data
}

export async function webSearch(query: string, maxResults = 5) {
    const response = await api.post<WebSearchResponse>('/api/v1/research/search', {
        query,
        max_results: maxResults,
    })
    return response.data
}

export async function deepResearch(query: string, maxResults = 6, maxPages = 3) {
    const response = await api.post<DeepResearchResponse>('/api/v1/research/deep', {
        query,
        max_results: maxResults,
        max_pages: maxPages,
    })
    return response.data
}

export async function generateImage(prompt: string, size = '1024x1024') {
    const response = await api.post<ImageResponse>('/api/v1/images/generate', { prompt, size })
    return response.data
}

export async function editImage(prompt: string, file: File, size = '1024x1024') {
    const form = new FormData()
    form.append('prompt', prompt)
    form.append('size', size)
    form.append('image', file)
    const response = await api.post<ImageResponse>('/api/v1/images/edit', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
}

export async function analyzeImage(prompt: string, file: File) {
    const form = new FormData()
    form.append('prompt', prompt)
    form.append('image', file)
    const response = await api.post<ImageAnalysisResponse>('/api/v1/images/analyze', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
}

export async function synthesizeSpeech(text: string, options: SpeechSynthesisOptions = {}) {
    const response = await api.post(
        '/api/v1/speech/synthesize',
        { text, voice: options.voice, rate: options.rate },
        { responseType: 'blob' },
    )
    return response.data as Blob
}
