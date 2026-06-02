import api from './request'

export interface UserProfile {
    id: string
    username: string
    email: string
    display_name: string
}

export interface WorkspaceSummary {
    id: string
    name: string
    invite_code: string
    role: string
    created_at: string
    updated_at: string
}

export interface AuthState {
    user: UserProfile
    workspaces: WorkspaceSummary[]
    current_workspace_id: string | null
}

export async function getAuthState() {
    const response = await api.get<AuthState>('/api/v1/auth/me')
    return response.data
}

export async function register(payload: { username: string; password: string; display_name?: string; email?: string }) {
    const response = await api.post<AuthState>('/api/v1/auth/register', payload)
    return response.data
}

export async function login(payload: { username: string; password: string }) {
    const response = await api.post<AuthState>('/api/v1/auth/login', payload)
    return response.data
}

export async function logout() {
    await api.post('/api/v1/auth/logout')
}

export async function createWorkspace(name: string) {
    const response = await api.post<WorkspaceSummary>('/api/v1/workspaces', { name })
    return response.data
}

export async function listWorkspaces() {
    const response = await api.get<WorkspaceSummary[]>('/api/v1/workspaces')
    return response.data
}

export async function joinWorkspace(workspaceId: string, inviteCode?: string) {
    const response = await api.post<WorkspaceSummary>(`/api/v1/workspaces/${workspaceId}/join`, {
        invite_code: inviteCode,
    })
    return response.data
}

export async function joinWorkspaceByInvite(inviteCode: string) {
    const response = await api.post<WorkspaceSummary>('/api/v1/workspaces/join', {
        invite_code: inviteCode,
    })
    return response.data
}
