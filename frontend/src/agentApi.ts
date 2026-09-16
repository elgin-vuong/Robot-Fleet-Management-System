import type { AgentChatResponse, AgentConfirmResponse } from './types'

export async function sendAgentMessage(token: string, message: string): Promise<AgentChatResponse> {
  const res = await fetch('/agent/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message }),
  })

  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `agent chat -> ${res.status}`)
  }

  return res.json() as Promise<AgentChatResponse>
}

export async function confirmAgentAction(token: string, confirmationId: string): Promise<AgentConfirmResponse> {
  const res = await fetch('/agent/confirm', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ confirmation_id: confirmationId }),
  })

  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `agent confirm -> ${res.status}`)
  }

  return res.json() as Promise<AgentConfirmResponse>
}

export async function resetAgentChat(token: string): Promise<void> {
  const res = await fetch('/agent/chat', {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })

  if (!res.ok) throw new Error(`agent reset -> ${res.status}`)
}
