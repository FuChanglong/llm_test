import type { Dispatch, SetStateAction } from 'react'
import type { ModalStaticFunctions } from 'antd/es/modal/confirm'
import type { MessageInstance } from 'antd/es/message/interface'

import type { ChatAttachment } from '@/api/chat'
import { analyzeAttachment, deleteSessionAttachment, uploadSessionAttachment } from '@/api/localFeatures'

export function useAttachmentActions(
    workspaceId: string | null,
    sessionId: string | null,
    setPendingAttachments: Dispatch<SetStateAction<ChatAttachment[]>>,
    message: MessageInstance,
    modal: Omit<ModalStaticFunctions, 'warn'>,
) {
    async function uploadAttachment(file: File) {
        if (!workspaceId || !sessionId) return
        try {
            const attachment = await uploadSessionAttachment(workspaceId, sessionId, file)
            setPendingAttachments((prev) => [...prev, attachment])
            if (attachment.status === 'error') message.warning(`${attachment.filename} 已上传，但解析失败`)
        } catch (err) {
            message.error(`上传附件失败: ${String(err)}`)
        }
    }

    async function removePendingAttachment(attachmentId: string) {
        if (!workspaceId || !sessionId) return
        setPendingAttachments((prev) => prev.filter((item) => item.id !== attachmentId))
        try {
            await deleteSessionAttachment(workspaceId, sessionId, attachmentId)
        } catch (err) {
            message.error(`删除附件失败: ${String(err)}`)
        }
    }

    async function runAttachmentAnalysis(attachmentId: string) {
        if (!workspaceId || !sessionId) return
        try {
            const result = await analyzeAttachment(workspaceId, sessionId, attachmentId)
            modal.info({
                title: `${result.filename} 数据分析`,
                width: 720,
                content: <pre className="analysis-output">{JSON.stringify(result, null, 2)}</pre>,
            })
        } catch (err) {
            message.error(`数据分析失败: ${String(err)}`)
        }
    }

    return { uploadAttachment, removePendingAttachment, runAttachmentAnalysis }
}
