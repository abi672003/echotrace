import { Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { AdminTokenProvider } from './context/AdminTokenContext'
import { HideNamesProvider } from './context/HideNamesContext'
import { AnalysisPage } from './pages/AnalysisPage'
import { CheckPage } from './pages/CheckPage'
import { DocketPage } from './pages/DocketPage'
import { DocketsPage } from './pages/DocketsPage'

function App() {
  return (
    <AdminTokenProvider>
      <HideNamesProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<DocketsPage />} />
            <Route path="/dockets/:docketId" element={<DocketPage />} />
            <Route path="/analyses/:analysisId" element={<AnalysisPage />} />
            <Route path="/check" element={<CheckPage />} />
          </Route>
        </Routes>
      </HideNamesProvider>
    </AdminTokenProvider>
  )
}

export default App
