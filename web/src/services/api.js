import { MOCK_PERSONAS, MOCK_REPLIES } from './mockData'

const USE_MOCK = true  // Toggle: true = mock data, false = real backend

export async function fetchPersonas() {
    if (USE_MOCK) return MOCK_PERSONAS

    const res = await fetch('/api/personas')
    const data = await res.json()
    return data.personas || []
}

export async function fetchDiscover(count = 5) {
    if (USE_MOCK) return MOCK_PERSONAS.slice(0, count)

    const res = await fetch(`/api/discover?count=${count}`)
    const data = await res.json()
    return data.candidates || []
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
