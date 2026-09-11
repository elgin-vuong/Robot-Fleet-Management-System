import type { AuthUser, Role } from './types'

export async function login(username: string, password: string): Promise<string> {
  const res = await fetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username, password }),
  })

  if (!res.ok) throw new Error('Invalid username or password')

  const data = (await res.json()) as { access_token: string }
  return data.access_token
}

export async function fetchMe(token: string): Promise<AuthUser> {
  const res = await fetch('/auth/me', {
    headers: { Authorization: `Bearer ${token}` },
  })

  if (!res.ok) throw new Error(`/auth/me -> ${res.status}`)

  return res.json() as Promise<AuthUser>
}

export async function fetchUsers(token: string): Promise<AuthUser[]> {
  const res = await fetch('/auth/users', {
    headers: { Authorization: `Bearer ${token}` },
  })

  if (!res.ok) throw new Error(`/auth/users -> ${res.status}`)

  return res.json() as Promise<AuthUser[]>
}

export async function createUser(
  token: string,
  input: { username: string; password: string; role: Role },
): Promise<AuthUser> {
  const res = await fetch('/auth/users', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(input),
  })

  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `create user -> ${res.status}`)
  }

  return res.json() as Promise<AuthUser>
}
