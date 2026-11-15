import { Navigate, Route, Routes } from 'react-router-dom'
import { NavBar } from './components/NavBar'
import { ToastContainer } from './components/ToastContainer'
import { getLastBatchId } from './lib/lastBatch'
import { BatchPage } from './routes/BatchPage'
import { HistoryPage } from './routes/HistoryPage'
import { UploadPage } from './routes/UploadPage'

function RootRedirect() {
  return <Navigate to={getLastBatchId() ? '/history' : '/upload'} replace />
}

function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <NavBar />
      <main>
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/batches/:batchId" element={<BatchPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <ToastContainer />
    </div>
  )
}

export default App
