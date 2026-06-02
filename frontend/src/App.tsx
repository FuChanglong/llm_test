import { useState } from 'react'
import { App as AntApp, Card, Drawer, Grid, Layout } from 'antd'

import './App.css'
import { AuthPage, WorkspaceAccessPage } from './components/AuthPage'
import CanvasDrawer from './components/CanvasDrawer'
import ChatHeader from './components/ChatHeader'
import ChatInput from './components/ChatInput'
import ChatSearchDrawer from './components/ChatSearchDrawer'
import ImageStudioDrawer from './components/ImageStudioDrawer'
import KnowledgeBasePage from './components/KnowledgeBasePage'
import MemoryDrawer from './components/MemoryDrawer'
import MessageList from './components/MessageList'
import RagDebugPanel from './components/RagDebugPanel'
import ResearchDrawer from './components/ResearchDrawer'
import SettingsModal from './components/SettingsModal'
import Sidebar from './components/Sidebar'
import type { AppView } from './components/Sidebar'
import WorkspaceOverviewPage from './components/WorkspaceOverviewPage'
import { useAttachmentActions } from './features/attachments/useAttachmentActions'
import { useAuthWorkspace } from './features/auth/useAuthWorkspace'
import { useChatWorkspace } from './features/chat/useChatWorkspace'
import { useSpeechPlaybackSettings } from './features/chat/speechSettings'
import { usePanels } from './features/panels/usePanels'
import { useUserPreferences } from './features/settings/useUserPreferences'

const { Sider, Content } = Layout

function App() {
  const { message, modal } = AntApp.useApp()
  const screens = Grid.useBreakpoint()
  const mobile = !screens.lg
  const auth = useAuthWorkspace(message)
  const panels = usePanels()
  const [activeView, setActiveView] = useState<AppView>('chat')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const speech = useSpeechPlaybackSettings()
  const userPreferences = useUserPreferences()
  const chat = useChatWorkspace(auth.currentWorkspaceId, message, modal, userPreferences.preferences.defaultChatMode)
  const attachments = useAttachmentActions(
    auth.currentWorkspaceId,
    chat.currentSessionId,
    chat.setPendingAttachments,
    message,
    modal,
  )

  async function handleLogout() {
    setSettingsOpen(false)
    setSearchOpen(false)
    panels.setSidebarOpen(false)
    await auth.handleLogout()
  }

  if (auth.authLoading) {
    return <div className="auth-shell"><div className="auth-loading">正在初始化工作台...</div></div>
  }

  if (!auth.user) {
    return (
      <AuthPage
        mode={auth.authMode}
        username={auth.authUsername}
        email={auth.authEmail}
        password={auth.authPassword}
        displayName={auth.authDisplayName}
        confirmPassword={auth.authConfirmPassword}
        submitting={auth.authSubmitting}
        errorMessage={auth.authErrorMessage}
        onModeChange={auth.setAuthMode}
        onUsernameChange={auth.setAuthUsername}
        onEmailChange={auth.setAuthEmail}
        onPasswordChange={auth.setAuthPassword}
        onDisplayNameChange={auth.setAuthDisplayName}
        onConfirmPasswordChange={auth.setAuthConfirmPassword}
        onSubmit={() => void auth.submitAuth()}
      />
    )
  }

  if (!auth.currentWorkspaceId) {
    return (
      <WorkspaceAccessPage
        userName={auth.user.display_name}
        workspaceDraft={auth.workspaceDraft}
        inviteDraft={auth.inviteDraft}
        onWorkspaceDraftChange={auth.setWorkspaceDraft}
        onInviteDraftChange={auth.setInviteDraft}
        onCreateWorkspace={() => void auth.handleCreateWorkspace()}
        onJoinWorkspace={() => void auth.handleJoinWorkspace()}
      />
    )
  }

  return (
    <div className={userPreferences.preferences.compactSidebar ? 'app-shell compact-sidebar' : 'app-shell'}>
      <Layout className="page">
        {!mobile && (
          <Sider width={260} theme="light" className="sidebar">
            <Sidebar
              activeView={activeView}
              sessions={chat.sessions}
              currentSessionId={chat.currentSessionId}
              loading={chat.loadingSessions}
              workspaceId={auth.currentWorkspaceId}
              workspaces={auth.workspaces}
              userName={auth.user.display_name}
              workspaceDraft={auth.workspaceDraft}
              inviteDraft={auth.inviteDraft}
              onChangeView={setActiveView}
              onNewSession={chat.createSessionInWorkspace}
              onOpenSearch={() => setSearchOpen(true)}
              onSelectSession={chat.setCurrentSessionId}
              onDeleteSession={chat.deleteSession}
              onChangeWorkspace={auth.setCurrentWorkspaceId}
              onWorkspaceDraftChange={auth.setWorkspaceDraft}
              onInviteDraftChange={auth.setInviteDraft}
              onCreateWorkspace={() => void auth.handleCreateWorkspace()}
              onJoinWorkspace={() => void auth.handleJoinWorkspace()}
              onOpenResearch={() => panels.setResearchOpen(true)}
              onOpenImages={() => panels.setImagesOpen(true)}
              onOpenCanvas={() => panels.setCanvasOpen(true)}
              onOpenMemory={() => panels.setMemoryOpen(true)}
              onOpenRagDebug={() => panels.setRagDebugOpen(true)}
              onOpenSettings={() => setSettingsOpen(true)}
              onLogout={() => void handleLogout()}
            />
          </Sider>
        )}
        <Layout className="main-layout">
          <ChatHeader
            mobile={mobile}
            activeView={activeView}
            workspaceId={auth.currentWorkspaceId}
            workspaces={auth.workspaces}
            onOpenSidebar={() => panels.setSidebarOpen(true)}
            onOpenSettings={() => setSettingsOpen(true)}
            onOpenKnowledge={() => setActiveView('knowledge')}
            onShare={() => void shareWorkspaceLink(message)}
            onExport={chat.exportCurrentSession}
          />
          <Content className="content">
            {activeView === 'chat' ? (
              <Card className="chat-card">
                <MessageList
                  currentSession={chat.currentSession}
                  onFillPrompt={chat.setInput}
                  onEditMessage={chat.editMessage}
                  onRegenerateMessage={chat.regenerateMessage}
                  onSendToCanvas={panels.sendToCanvas}
                  onSaveMemory={chat.saveAsMemory}
                  speechSettings={speech.settings}
                  isStreamingReply={chat.loadingChat}
                  mobile={mobile}
                  fontScale={userPreferences.preferences.messageFontScale}
                />
                <ChatInput
                  input={chat.input}
                  setInput={chat.setInput}
                  loading={chat.loadingChat}
                  currentSessionId={chat.currentSessionId}
                  chatMode={chat.chatMode}
                  toolsEnabled={userPreferences.preferences.appIntegrations}
                  pendingAttachments={chat.pendingAttachments}
                  onSend={chat.sendMessage}
                  onStop={chat.stopGeneration}
                  onChatModeChange={chat.setChatMode}
                  onOpenResearch={() => panels.setResearchOpen(true)}
                  onOpenImages={() => panels.setImagesOpen(true)}
                  onOpenCanvas={() => panels.setCanvasOpen(true)}
                  onOpenMemory={() => panels.setMemoryOpen(true)}
                  onOpenRagDebug={() => panels.setRagDebugOpen(true)}
                  onExport={chat.exportCurrentSession}
                  mobile={mobile}
                  sendKeyMode={userPreferences.preferences.sendKeyMode}
                  speechSettings={speech.settings}
                  onSpeechSettingsChange={speech.updateSettings}
                  onUploadAttachment={attachments.uploadAttachment}
                  onRemoveAttachment={(attachmentId) => { void attachments.removePendingAttachment(attachmentId) }}
                  onAnalyzeAttachment={(attachmentId) => { void attachments.runAttachmentAnalysis(attachmentId) }}
                />
              </Card>
            ) : activeView === 'knowledge' ? (
              <KnowledgeBasePage
                workspaceId={auth.currentWorkspaceId}
                onUseInChat={(text) => {
                  chat.setInput(text)
                  setActiveView('chat')
                }}
              />
            ) : (
              <WorkspaceOverviewPage
                workspaceId={auth.currentWorkspaceId}
                onOpenChat={() => setActiveView('chat')}
                onOpenKnowledge={() => setActiveView('knowledge')}
              />
            )}
          </Content>
        </Layout>
      </Layout>
      <Drawer title={null} placement="left" open={mobile && panels.sidebarOpen} onClose={() => panels.setSidebarOpen(false)} width="86vw" className="mobile-sidebar-drawer" styles={{ body: { padding: 0 } }}>
        <Sidebar
          activeView={activeView}
          sessions={chat.sessions}
          currentSessionId={chat.currentSessionId}
          loading={chat.loadingSessions}
          workspaceId={auth.currentWorkspaceId}
          workspaces={auth.workspaces}
          userName={auth.user.display_name}
          workspaceDraft={auth.workspaceDraft}
          inviteDraft={auth.inviteDraft}
          onChangeView={(view) => { setActiveView(view); panels.setSidebarOpen(false) }}
          onNewSession={chat.createSessionInWorkspace}
          onOpenSearch={() => { setSearchOpen(true); panels.setSidebarOpen(false) }}
          onSelectSession={chat.setCurrentSessionId}
          onDeleteSession={chat.deleteSession}
          onChangeWorkspace={auth.setCurrentWorkspaceId}
          onWorkspaceDraftChange={auth.setWorkspaceDraft}
          onInviteDraftChange={auth.setInviteDraft}
          onCreateWorkspace={() => void auth.handleCreateWorkspace()}
          onJoinWorkspace={() => void auth.handleJoinWorkspace()}
          onOpenResearch={() => { panels.setResearchOpen(true); panels.setSidebarOpen(false) }}
          onOpenImages={() => { panels.setImagesOpen(true); panels.setSidebarOpen(false) }}
          onOpenCanvas={() => { panels.setCanvasOpen(true); panels.setSidebarOpen(false) }}
          onOpenMemory={() => { panels.setMemoryOpen(true); panels.setSidebarOpen(false) }}
          onOpenRagDebug={() => { panels.setRagDebugOpen(true); panels.setSidebarOpen(false) }}
          onOpenSettings={() => { setSettingsOpen(true); panels.setSidebarOpen(false) }}
          onLogout={() => void handleLogout()}
        />
      </Drawer>
      <SettingsModal
        open={settingsOpen}
        mobile={mobile}
        userName={auth.user.display_name}
        speechSettings={speech.settings}
        preferences={userPreferences.preferences}
        onClose={() => setSettingsOpen(false)}
        onSpeechSettingsChange={speech.updateSettings}
        onPreferencesChange={userPreferences.updatePreferences}
        onOpenMemory={() => { setSettingsOpen(false); panels.setMemoryOpen(true) }}
        onOpenRagDebug={() => { setSettingsOpen(false); panels.setRagDebugOpen(true) }}
        onLogout={() => void handleLogout()}
      />
      <RagDebugPanel open={panels.ragDebugOpen} workspaceId={auth.currentWorkspaceId} onClose={() => panels.setRagDebugOpen(false)} />
      <ChatSearchDrawer
        open={searchOpen}
        sessions={chat.sessions}
        currentSessionId={chat.currentSessionId}
        onClose={() => setSearchOpen(false)}
        onSelectSession={(sessionId) => {
          setActiveView('chat')
          chat.setCurrentSessionId(sessionId)
        }}
      />
      <MemoryDrawer open={panels.memoryOpen} onClose={() => panels.setMemoryOpen(false)} />
      <ResearchDrawer open={panels.researchOpen} onClose={() => panels.setResearchOpen(false)} onUseInChat={(text) => { chat.setInput(text); panels.setResearchOpen(false) }} />
      <ImageStudioDrawer open={panels.imagesOpen} onClose={() => panels.setImagesOpen(false)} />
      <CanvasDrawer
        key={panels.canvasVersion}
        open={panels.canvasOpen}
        workspaceId={auth.currentWorkspaceId}
        sessionId={chat.currentSessionId}
        seedContent={panels.canvasSeed}
        onClose={() => panels.setCanvasOpen(false)}
        onSeedConsumed={() => panels.setCanvasSeed('')}
      />
    </div>
  )
}

async function shareWorkspaceLink(message: ReturnType<typeof AntApp.useApp>['message']) {
  const url = window.location.href
  try {
    if (navigator.share) {
      await navigator.share({ title: '知识库问答工作台', url })
      return
    }
    await navigator.clipboard.writeText(url)
    message.success('页面链接已复制')
  } catch {
    message.error('分享失败，请稍后再试')
  }
}

export default App
