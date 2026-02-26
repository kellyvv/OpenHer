import { useState, useEffect, useRef, useCallback } from 'react'
import { getWsUrl } from '../services/api'

export function useWebSocket() {
    const wsRef = useRef(null)
    const [connected, setConnected] = useState(false)
    const [messages, setMessages] = useState([])
    const [streaming, setStreaming] = useState(false)
    const [sessionId, setSessionId] = useState(null)
    const [status, setStatus] = useState({})
    const streamContentRef = useRef('')

    const connect = useCallback(() => {
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
                    setStreaming(true)
                    streamContentRef.current = ''
                    setMessages(prev => [...prev, { role: 'assistant', content: '', streaming: true }])
                    break

                case 'chat_chunk':
                    streamContentRef.current += msg.content
                    setMessages(prev => {
                        const updated = [...prev]
                        const last = updated[updated.length - 1]
                        if (last?.streaming) {
                            updated[updated.length - 1] = { ...last, content: streamContentRef.current }
                        }
                        return updated
                    })
                    break

                case 'chat_end':
                    setStreaming(false)
                    setMessages(prev => {
                        const updated = [...prev]
                        const last = updated[updated.length - 1]
                        if (last?.streaming) {
                            updated[updated.length - 1] = { ...last, streaming: false }
                        }
                        return updated
                    })
                    setStatus({
                        dominantDrive: msg.dominant_drive,
                        turnCount: msg.turn_count,
                    })
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
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
        setMessages(prev => [...prev, { role: 'user', content: text }])
        wsRef.current.send(JSON.stringify({
            type: 'chat',
            content: text,
            persona_id: personaId,
            user_name: userName,
        }))
    }, [])

    const clearMessages = useCallback(() => {
        setMessages([])
        setSessionId(null)
    }, [])

    useEffect(() => {
        connect()
        return () => wsRef.current?.close()
    }, [connect])

    return { connected, messages, streaming, sessionId, status, sendMessage, clearMessages }
}
