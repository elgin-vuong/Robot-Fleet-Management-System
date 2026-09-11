import { useCallback, useEffect, useState, type FormEvent } from 'react'
import type { AuthUser, Role } from '../types'
import { createUser, fetchUsers } from '../authApi'
import { useAuth } from '../AuthContext'
import './UserManagement.css'

export function UserManagement() {
  const { token } = useAuth()
  const [users, setUsers] = useState<AuthUser[]>([])
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<Role>('viewer')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const load = useCallback(async () => {
    if (!token) return
    try {
      setUsers(await fetchUsers(token))
    } catch (err) {
      console.error('Failed to load users', err)
    }
  }, [token])

  useEffect(() => {
    load()
  }, [load])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!token) return

    setError(null)
    setSubmitting(true)

    try {
      await createUser(token, { username, password, role })
      setUsername('')
      setPassword('')
      setRole('viewer')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create user')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="user-management">
      <h3>User management</h3>

      <table className="user-management_table">
        <thead>
          <tr>
            <th scope="col">Username</th>
            <th scope="col">Role</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.username}</td>
              <td>{u.role}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <form className="user-management_form" onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
          <option value="viewer">Viewer</option>
          <option value="operator">Operator</option>
          <option value="admin">Admin</option>
        </select>
        <button type="submit" disabled={submitting}>
          {submitting ? 'Adding…' : 'Add user'}
        </button>
      </form>

      {error && <p className="user-management_error">{error}</p>}
    </div>
  )
}
