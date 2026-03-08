import { useState, useEffect, useRef, useCallback } from 'react'
import { getWsUrl, USE_MOCK, getMockReply, getClientId } from '../services/api'

export function useWebSocket() {
    const wsRef = useRef(null)
    const [connected, setConnected] = useState(USE_MOCK)
    const [messages, setMessages] = useState([])
    const [streaming, setStreaming] = useState(false)
    const [sessionId, setSessionId] = useState(null)
    const [status, setStatus] = useState({})
    const streamContentRef = useRef('')
    const typingTimerRef = useRef(null)
    const clientId = useRef(getClientId())

    const connect = useCallback(() => {
        if (USE_MOCK) {
            setConnected(true)
            return
        }

        if (wsRef.current?.readyState === WebSocket.OPEN) return
        const ws = new WebSocket(getWsUrl())
        wsRef.current = ws

        ws.onopen = () => setConnected(true)
        ws.onclose = () => {
            setConnected(false)
            setTimeout(connect, 3000)
        }
        ws.onerror = () => setConnected(false)

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data)
            switch (msg.type) {
                case 'chat_start':
                    setSessionId(msg.session_id)
                    streamContentRef.current = ''
                    // Delay showing typing indicator — feels natural (not instant)
                    typingTimerRef.current = setTimeout(() => {
                        setStreaming(true)
                    }, 1500)
                    break
                case 'chat_chunk':
                    // Buffer silently
                    streamContentRef.current += msg.content
                    break
                case 'chat_end':
                    // Cancel typing indicator timer if reply arrived fast
                    if (typingTimerRef.current) {
                        clearTimeout(typingTimerRef.current)
                        typingTimerRef.current = null
                    }
                    setStreaming(false)
                    if (msg.reply) {
                        setMessages(prev => [...prev, {
                            role: 'assistant',
                            content: msg.reply,
                        }])
                    }
                    console.log('[engine]', JSON.stringify(msg, null, 2))
                    setStatus(msg)
                    break
                case 'persona_switched':
                    setSessionId(msg.session_id)
                    break
                case 'error':
                    console.error('WS error:', msg.content)
                    setStreaming(false)
                    break
            }
        }
    }, [])

    const sendMessage = useCallback((text, personaId, userName = 'User') => {
        // Add user message
        setMessages(prev => [...prev, { role: 'user', content: text }])

        if (USE_MOCK) {
            // Simulate streaming response
            setStreaming(true)
            const reply = getMockReply(personaId)
            let i = 0
            setMessages(prev => [...prev, { role: 'assistant', content: '', streaming: true }])

            const interval = setInterval(() => {
                i += 2
                const partial = reply.slice(0, i)
                setMessages(prev => {
                    const updated = [...prev]
                    const last = updated[updated.length - 1]
                    if (last?.streaming) {
                        updated[updated.length - 1] = { ...last, content: partial }
                    }
                    return updated
                })
                if (i >= reply.length) {
                    clearInterval(interval)
                    setStreaming(false)
                    setMessages(prev => {
                        const updated = [...prev]
                        const last = updated[updated.length - 1]
                        if (last?.streaming) {
                            updated[updated.length - 1] = { ...last, streaming: false }
                        }
                        return updated
                    })
                    setStatus({ dominantDrive: '🔗 connection', turnCount: (status.turnCount || 0) + 1 })
                }
            }, 30)
            return
        }

        // Real WebSocket
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
        wsRef.current.send(JSON.stringify({
            type: 'chat', content: text, persona_id: personaId,
            user_name: userName, client_id: clientId.current,
        }))
    }, [status.turnCount])

    const clearMessages = useCallback(() => {
        setMessages([])
        setSessionId(null)
        setStatus({})
    }, [])

    const setInitialMessages = useCallback((msgsOrFn) => {
        setMessages(msgsOrFn)
    }, [])

    useEffect(() => {
        connect()
        return () => wsRef.current?.close()
    }, [connect])

    return { connected, messages, streaming, sessionId, status, sendMessage, clearMessages, setInitialMessages, clientId: clientId.current }
}
