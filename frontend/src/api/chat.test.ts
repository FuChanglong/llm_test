import { describe, expect, it, vi } from 'vitest'
import { parseChatStreamLine, streamChat, streamEditChat, streamRegenerateChat } from './chat'
import type { ChatStreamEvent } from './chat'

describe('parseChatStreamLine', () => {
    it('parses one NDJSON line into a stream event', () => {
        expect(parseChatStreamLine('{"type":"token","content":"hi"}')).toEqual({
            type: 'token',
            content: 'hi',
        })
    })

    it('throws a useful error for invalid JSON', () => {
        expect(() => parseChatStreamLine('{bad')).toThrow('Invalid chat stream event')
    })
})

describe('streamChat', () => {
    it('parses split NDJSON chunks in order', async () => {
        const encoder = new TextEncoder()
        const body = new ReadableStream({
            start(controller) {
                controller.enqueue(encoder.encode('{"type":"start"}\n{"type":"token","content":"hel'))
                controller.enqueue(encoder.encode('lo"}\n'))
                controller.close()
            },
        })
        const fetchMock = vi.fn(async () => new Response(body, { status: 200 }))
        vi.stubGlobal('fetch', fetchMock)

        const events: ChatStreamEvent[] = []
        await streamChat(
            { session_id: 'abc123def456', message: 'hello' },
            (event) => events.push(event),
        )

        expect(events).toEqual([
            { type: 'start' },
            { type: 'token', content: 'hello' },
        ])
    })

    it('passes AbortSignal to fetch', async () => {
        const controller = new AbortController()
        const fetchMock = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
            expect(init?.signal).toBe(controller.signal)
            throw new DOMException('Aborted', 'AbortError')
        })
        vi.stubGlobal('fetch', fetchMock)

        await expect(
            streamChat(
                { session_id: 'abc123def456', message: 'hello' },
                () => undefined,
                controller.signal,
            ),
        ).rejects.toThrow('Aborted')
    })

    it('uses dedicated endpoints for edit and regenerate streams', async () => {
        const fetchMock = vi.fn(async () => new Response('{"type":"start"}\n', { status: 200 }))
        vi.stubGlobal('fetch', fetchMock)

        await streamEditChat(
            { session_id: 'abc123def456', message_id: 'def123abc456', message: 'edited' },
            () => undefined,
        )
        await streamRegenerateChat(
            { session_id: 'abc123def456', message_id: 'def123abc456' },
            () => undefined,
        )

        const calls = fetchMock.mock.calls as unknown as Array<[string | URL | Request, RequestInit?]>
        expect(String(calls[0][0])).toContain('/api/v1/chat/edit/stream')
        expect(String(calls[1][0])).toContain('/api/v1/chat/regenerate/stream')
    })
})
