import React from 'react'
import { Button } from 'antd'
import { DeleteOutlined, MessageOutlined } from '@ant-design/icons'
import type { SessionSummary } from '@/api/session'

interface SessionItemProps {
    session: SessionSummary
    isActive: boolean
    onSelect: (sessionId: string) => void
    onDelete: (sessionId: string) => void
}

const SessionItem: React.FC<SessionItemProps> = ({
    session,
    isActive,
    onSelect,
    onDelete
}) => {
    return (
        <div
            className={`session-item ${isActive ? 'active' : ''}`}
            onClick={() => onSelect(session.id)}
        >
            <MessageOutlined className="session-item-avatar" />
            <div className="session-item-content">
                <div className="session-item-title">{session.title}</div>
            </div>
            <div className="session-item-actions">
                <Button
                    type="text"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    className="session-item-delete-btn"
                    onClick={(e) => {
                        e.stopPropagation()
                        onDelete(session.id)
                    }}
                />
            </div>
        </div>
    )
}

export default SessionItem
