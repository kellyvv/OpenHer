import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ChevronLeft, SendHorizontal, User } from 'lucide-react'
import { fetchPersonas, fetchChatHistory } from '../services/api'
import { useWebSocket } from '../hooks/useWebSocket'
import './Chat.css'

export default function Chat() {
    const { personaId } = useParams()
    const navigate = useNavigate()
    const [persona, setPersona] = useState(null)
    const [input, setInput] = useState('')
    const messagesRef = useRef(null)
    const inputRef = useRef(null)
    const { connected, messages, streaming, status, sendMessage, clearMessages, setInitialMessages, clientId } = useWebSocket()

    useEffect(() => {
        fetchPersonas().then(list => {
            const found = list.find(p => p.persona_id === personaId)
            if (found) setPersona(found)
        })
        clearMessages()
    }, [personaId, clearMessages])

    // Load chat history on mount (display-only, does not affect engine)
    useEffect(() => {
        if (!personaId || !clientId) return
        let cancelled = false
        fetchChatHistory(personaId, clientId, 50).then(msgs => {
            // Guard 1: stale fetch (persona switched before response arrived)
            if (cancelled) return
            // Guard 2: user already sent a message before fetch resolved
            if (msgs && msgs.length > 0) {
                setInitialMessages(prev => {
                    if (prev.length > 0) return prev  // don't clobber live state
                    return msgs.map(m => ({ role: m.role, content: m.content }))
                })
            }
        })
        return () => { cancelled = true }
    }, [personaId, clientId, setInitialMessages])

    useEffect(() => {
        if (messagesRef.current) {
            messagesRef.current.scrollTop = messagesRef.current.scrollHeight
        }
    }, [messages])

    const handleSend = () => {
        const text = input.trim()
        if (!text || streaming) return
        sendMessage(text, personaId)
        setInput('')
        inputRef.current?.focus()
    }

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            handleSend()
        }
    }

    const bio = persona?.bio
        ? (typeof persona.bio === 'object' ? (persona.bio.en || '') : persona.bio)
        : ''

    return (
        <div className="chat-page">
            {/* Ambient background from persona photo */}
            {persona?.avatar_url && (
                <div className="chat-ambient">
                    <img src={persona.avatar_url} alt="" className="chat-ambient-img" draggable={false} />
                </div>
            )}

            {/* Header */}
            <header className="chat-header">
                <button className="back-btn" onClick={() => navigate('/discover')}>
                    <ChevronLeft size={24} />
                </button>
                <div className="header-title">
                    {streaming
                        ? <span className="header-typing">对方正在输入<span className="header-typing-dots"><span /><span /><span /></span></span>
                        : (persona?.name || 'Loading...')
                    }
                </div>
                <div style={{ width: 32 }} />
            </header>

            {/* Messages */}
            <div className="messages" ref={messagesRef}>
                {messages.length === 0 && (
                    <div className="welcome">
                        <div className="welcome-avatar">
                            {persona?.avatar_url ? (
                                <img src={persona.avatar_url} alt="" className="welcome-avatar-img" />
                            ) : (
                                persona?.name?.[0] || '✦'
                            )}
                        </div>
                        <h2>{persona?.name || 'AI Companion'}</h2>
                        <p className="welcome-bio">{bio}</p>
                        {persona?.tags && (
                            <div className="welcome-tags">
                                {persona.tags.map((t, i) => (
                                    <span key={i} className="welcome-tag">{t}</span>
                                ))}
                            </div>
                        )}
                        <p className="welcome-hint">Say something to start a conversation</p>
                    </div>
                )}

                {messages.map((msg, i) => (
                    <div key={i} className={`message ${msg.role}`}>
                        <div className="msg-avatar">
                            {msg.role === 'user' ? (
                                <User size={18} />
                            ) : persona?.avatar_url ? (
                                <img src={persona.avatar_url} alt="" className="msg-avatar-img" />
                            ) : (
                                <span>{persona?.name?.[0] || '✦'}</span>
                            )}
                        </div>
                        <div className="bubble">
                            {msg.content}
                        </div>
                    </div>
                ))}
            </div>

            {/* Input */}
            <div className="input-area">
                <div className="input-wrapper">
                    <input
                        ref={inputRef}
                        type="text"
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Say something..."
                        autoComplete="off"
                        disabled={streaming}
                    />
                    <button
                        className="send-btn"
                        onClick={handleSend}
                        disabled={streaming || !input.trim()}
                    >
                        <SendHorizontal size={20} />
                    </button>
                </div>
            </div>
        </div>
    )
}
