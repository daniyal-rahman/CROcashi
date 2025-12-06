import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import CompanyRiskDashboard from './pages/CompanyRiskDashboard'
import './App.css'

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<CompanyRiskDashboard />} />
        <Route path="/company/:companyId" element={<CompanyRiskDashboard />} />
      </Routes>
    </Router>
  )
}

export default App

