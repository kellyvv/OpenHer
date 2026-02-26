import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { fetchPersonas } from '../services/api'
import { useWebSocket } from '../hooks/useWebSocket'
import './Chat.css'

export default function Chat() {
    const { personaId } = useParams()
    const navigate = useNavigate()
    const [persona, setPersona] = useState(null)
    const [input, setInput] = useState('')
    const messagesRef = useRef(null)
    const inputRef = useRef(null)
    const { connected, messages, streaming, status, sendMessage, clearMessages } = useWebSocket()

    useEffect(() => {
        fetchPersonas().then(list => {
            const found = list.find(p => p.persona_id === personaId)
            if (found) setPersona(found)
        })
        clearMessages()
    }, [personaId, clearMessages])

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

            {/* Header */}
            <header className="chat-header">
                <button className="back-btn" onClick={() => navigate('/discover')}>
                    ←
                </button>
                <div className="header-avatar">
                    {persona?.name?.[0] || '?'}
                </div>
                <div className="header-info">
                    <div className="header-name">{persona?.name || 'Loading...'}</div>
                    <div className="header-detail">
                        {persona?.mbti && <span className="header-mbti">{persona.mbti}</span>}
                        {status.dominantDrive && <span className="header-drive">{status.dominantDrive}</span>}
                    </div>
                </div>
                <div className={`connection-dot ${connected ? 'connected' : 'disconnected'}`} />
            </header>

            {/* Messages */}
            <div className="messages" ref={messagesRef}>
                {messages.length === 0 && (
                    <div className="welcome">
                        <div className="welcome-avatar">
                            {persona?.name?.[0] || '✦'}
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
                        <p className="welcome-hint">Say something to start the conversation</p>
                    </div>
                )}

                {messages.map((msg, i) => (
                    <div key={i} className={`message ${msg.role}`}>
                        <div className="msg-avatar">
                            {msg.role === 'user' ? '👤' : (persona?.name?.[0] || '✦')}
                        </div>
                        <div className="bubble">
                            {msg.content}
                            {msg.streaming && <span className="cursor-blink">▊</span>}
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
                        ↑
                    </button>
                </div>
            </div>
        </div>
    )
}
