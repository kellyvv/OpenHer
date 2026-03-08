import { MOCK_PERSONAS, MOCK_REPLIES } from './mockData'

const USE_MOCK = false  // Toggle: true = mock data, false = real backend

export async function fetchPersonas() {
    if (USE_MOCK) return MOCK_PERSONAS

    try {
        const res = await fetch('/api/personas')
        const data = await res.json()
        // Map backend PersonaInfo fields to frontend format
        return (data.personas || []).map(p => ({
            ...p,
            bio: p.description || '',
        }))
    } catch (err) {
        console.warn('Backend unavailable, falling back to mock:', err.message)
        return MOCK_PERSONAS
    }
}

export async function fetchDiscover(count = 5) {
    if (USE_MOCK) return MOCK_PERSONAS.slice(0, count)

    try {
        const res = await fetch(`/api/discover?count=${count}`)
        const data = await res.json()
        return data.candidates || []
    } catch (err) {
        console.warn('Discover fallback to mock:', err.message)
        return MOCK_PERSONAS.slice(0, count)
    }
}

export async function selectPersona(personaId) {
    if (USE_MOCK) return { ok: true, persona_id: personaId }

    const res = await fetch(`/api/persona/select/${personaId}`, { method: 'POST' })
    return res.json()
}

export function getWsUrl() {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${window.location.host}/ws/chat`
}

// Mock chat helper
export function getMockReply(personaId) {
    const replies = MOCK_REPLIES[personaId] || MOCK_REPLIES.vivian
    return replies[Math.floor(Math.random() * replies.length)]
}

export { USE_MOCK }

/**
 * Stable client identity for chat log persistence (display-only).
 * Stored in localStorage, survives page refreshes and tab closures.
 * Completely separate from engine's stable_user_id.
 */
export function getClientId() {
    let id = localStorage.getItem('openher_client_id')
    if (!id) {
        id = crypto.randomUUID()
        localStorage.setItem('openher_client_id', id)
    }
    return id
}

/**
 * Fetch chat history from backend for display.
 */
export async function fetchChatHistory(personaId, clientId, limit = 50) {
    if (USE_MOCK) return []

    try {
        const params = new URLSearchParams({ client_id: clientId, limit: String(limit) })
        const res = await fetch(`/api/chat/history/${personaId}?${params}`)
        const data = await res.json()
        return data.messages || []
    } catch (err) {
        console.warn('Failed to load chat history:', err.message)
        return []
    }
}
