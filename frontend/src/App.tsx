import { useAuth } from './AuthContext'
import { LoginPage } from './components/LoginPage'
import Dashboard from './Dashboard'

function App() {
  const { status } = useAuth()

  if (status === 'loading') {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>Loading…</p>
      </div>
    )
  }

  if (status === 'unauthenticated') {
    return <LoginPage />
  }

  return <Dashboard />
}

export default App
