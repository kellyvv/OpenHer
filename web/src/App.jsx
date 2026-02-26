import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Discover from './pages/Discover'
import Chat from './pages/Chat'
import './index.css'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/discover" replace />} />
        <Route path="/discover" element={<Discover />} />
        <Route path="/chat/:personaId" element={<Chat />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
