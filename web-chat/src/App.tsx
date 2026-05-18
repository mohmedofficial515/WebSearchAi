import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import ChatPage from './routes/ChatPage'

export default function App() {
  return (
    <BrowserRouter basename="/chat">
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
