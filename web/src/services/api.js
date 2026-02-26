const API_BASE = ''  // Use Vite proxy in dev

export async function fetchPersonas() {
    const res = await fetch(`${API_BASE}/api/personas`)
    const data = await res.json()
    return data.personas || []
}

export async function fetchDiscover(count = 5) {
    const res = await fetch(`${API_BASE}/api/discover?count=${count}`)
    const data = await res.json()
    return data.candidates || []
}

export async function selectPersona(personaId) {
    const res = await fetch(`${API_BASE}/api/persona/select/${personaId}`, {
        method: 'POST',
    })
    return res.json()
}

export function getWsUrl() {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${window.location.host}/ws/chat`
}

export { API_BASE }
