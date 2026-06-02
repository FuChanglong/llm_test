import { useEffect, useState } from 'react'
import type { MessageInstance } from 'antd/es/message/interface'

import { getErrorMessage } from '@/api/errors'
import type { UserProfile, WorkspaceSummary } from '@/api/auth'
import { createWorkspace, getAuthState, joinWorkspaceByInvite, login, logout, register } from '@/api/auth'
import { validateAuthForm } from './authValidation'

const LAST_AUTH_USERNAME_KEY = 'llm_test_last_auth_username_v1'

export function useAuthWorkspace(message: MessageInstance) {
    const [authLoading, setAuthLoading] = useState(true)
    const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
    const [authUsername, setAuthUsername] = useState(() => loadLastAuthUsername())
    const [authEmail, setAuthEmail] = useState('')
    const [authPassword, setAuthPassword] = useState('')
    const [authDisplayName, setAuthDisplayName] = useState('')
    const [authConfirmPassword, setAuthConfirmPassword] = useState('')
    const [authErrorMessage, setAuthErrorMessage] = useState<string | null>(null)
    const [authSubmitting, setAuthSubmitting] = useState(false)
    const [workspaceDraft, setWorkspaceDraft] = useState('')
    const [inviteDraft, setInviteDraft] = useState(() => loadInviteDraftFromLocation())
    const [user, setUser] = useState<UserProfile | null>(null)
    const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([])
    const [currentWorkspaceId, setCurrentWorkspaceId] = useState<string | null>(null)

    useEffect(() => {
        try {
            window.localStorage.setItem(LAST_AUTH_USERNAME_KEY, authUsername.trim())
        } catch {
            // ignore storage failures
        }
    }, [authUsername])

    useEffect(() => {
        let cancelled = false
        getAuthState()
            .then((state) => {
                if (cancelled) return
                setUser(state.user)
                setWorkspaces(state.workspaces)
                setCurrentWorkspaceId(state.current_workspace_id)
            })
            .catch(() => {
                if (cancelled) return
                setUser(null)
                setWorkspaces([])
                setCurrentWorkspaceId(null)
            })
            .finally(() => {
                if (!cancelled) setAuthLoading(false)
            })
        return () => {
            cancelled = true
        }
    }, [])

    async function submitAuth() {
        const validation = validateAuthForm(authMode, authUsername, authPassword, authEmail, authDisplayName, authConfirmPassword)
        if (!validation.canSubmit) {
            setAuthErrorMessage(validation.error)
            return
        }
        setAuthSubmitting(true)
        setAuthErrorMessage(null)
        try {
            const state = authMode === 'login'
                ? await login({ username: authUsername, password: authPassword })
                : await register({
                    username: authUsername,
                    email: authEmail || undefined,
                    password: authPassword,
                    display_name: authDisplayName || undefined,
                })
            setUser(state.user)
            setWorkspaces(state.workspaces)
            setCurrentWorkspaceId(state.current_workspace_id)
            setAuthPassword('')
            setAuthConfirmPassword('')
            setAuthEmail('')
            setAuthDisplayName('')
        } catch (err) {
            const errorMessage = getErrorMessage(err, '认证失败，请检查账号信息或稍后再试')
            setAuthErrorMessage(errorMessage)
            message.error(`认证失败: ${errorMessage}`)
        } finally {
            setAuthSubmitting(false)
        }
    }

    async function handleLogout() {
        try {
            await logout()
        } finally {
            setUser(null)
            setWorkspaces([])
            setCurrentWorkspaceId(null)
        }
    }

    async function handleCreateWorkspace() {
        const name = workspaceDraft.trim()
        if (!name) return
        try {
            const workspace = await createWorkspace(name)
            const next = [...workspaces, workspace]
            setWorkspaces(next)
            setCurrentWorkspaceId(workspace.id)
            setWorkspaceDraft('')
        } catch (err) {
            message.error(`创建工作区失败: ${getErrorMessage(err)}`)
        }
    }

    async function handleJoinWorkspace() {
        const inviteCode = inviteDraft.trim()
        if (!inviteCode) return
        try {
            const workspace = await joinWorkspaceByInvite(inviteCode)
            const next = [
                workspace,
                ...workspaces.filter((item) => item.id !== workspace.id),
            ]
            setWorkspaces(next)
            setCurrentWorkspaceId(workspace.id)
            setInviteDraft('')
        } catch (err) {
            message.error(`加入工作区失败: ${getErrorMessage(err)}`)
        }
    }

    function updateMode(mode: 'login' | 'register') {
        setAuthErrorMessage(null)
        setAuthMode(mode)
    }

    function updateAuthUsername(value: string) {
        setAuthErrorMessage(null)
        setAuthUsername(value)
    }

    function updateAuthEmail(value: string) {
        setAuthErrorMessage(null)
        setAuthEmail(value)
    }

    function updateAuthPassword(value: string) {
        setAuthErrorMessage(null)
        setAuthPassword(value)
    }

    function updateAuthDisplayName(value: string) {
        setAuthErrorMessage(null)
        setAuthDisplayName(value)
    }

    function updateAuthConfirmPassword(value: string) {
        setAuthErrorMessage(null)
        setAuthConfirmPassword(value)
    }

    return {
        authLoading,
        authMode,
        authUsername,
        authEmail,
        authPassword,
        authDisplayName,
        authConfirmPassword,
        authErrorMessage,
        authSubmitting,
        workspaceDraft,
        inviteDraft,
        user,
        workspaces,
        currentWorkspaceId,
        setAuthMode: updateMode,
        setAuthUsername: updateAuthUsername,
        setAuthEmail: updateAuthEmail,
        setAuthPassword: updateAuthPassword,
        setAuthDisplayName: updateAuthDisplayName,
        setAuthConfirmPassword: updateAuthConfirmPassword,
        setWorkspaceDraft,
        setInviteDraft,
        setCurrentWorkspaceId,
        submitAuth,
        handleLogout,
        handleCreateWorkspace,
        handleJoinWorkspace,
    }
}

function loadLastAuthUsername() {
    try {
        return window.localStorage.getItem(LAST_AUTH_USERNAME_KEY) || ''
    } catch {
        return ''
    }
}

function loadInviteDraftFromLocation() {
    if (typeof window === 'undefined') return ''
    return new URLSearchParams(window.location.search).get('invite')?.trim() || ''
}
