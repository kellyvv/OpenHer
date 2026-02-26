import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Discover from './pages/Discover'
import Chat from './pages/Chat'
import './index.css'

function App() {
  return (
    <BrowserRouter>
      {/* Phone-frame wrapper: 9:16 on desktop, full-screen on mobile */}
      <div className="phone-frame">
        <div className="phone-screen">
          <div className="bg-orbs" />
          <Routes>
            <Route path="/" element={<Navigate to="/discover" replace />} />
            <Route path="/discover" element={<Discover />} />
            <Route path="/chat/:personaId" element={<Chat />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  )
}

export default App
