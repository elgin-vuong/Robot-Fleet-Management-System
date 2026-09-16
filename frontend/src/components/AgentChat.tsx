import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useAuth } from '../AuthContext'
import { confirmAgentAction, resetAgentChat, sendAgentMessage } from '../agentApi'
import type { AgentToolCall } from '../types'
import './AgentChat.css'

interface ChatMessage {
  id: number
  role: 'user' | 'assistant' | 'system'
  text: string
  toolCalls?: AgentToolCall[]
  confirmationId?: string | null
  confirmationResolved?: boolean
}

let nextId = 1

export function AgentChat() {
  const { token } = useAuth()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const logRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight })
  }, [messages])

  const appendMessage = (msg: Omit<ChatMessage, 'id'>) => {
    setMessages((prev) => [...prev, { ...msg, id: nextId++ }])
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!token || !input.trim() || sending) return

    const text = input.trim()
    setInput('')
    appendMessage({ role: 'user', text })
    setSending(true)

    try {
      const result = await sendAgentMessage(token, text)
      appendMessage({
        role: 'assistant',
        text: result.response,
        toolCalls: result.tool_calls,
        confirmationId: result.requires_confirmation ? result.confirmation_id : undefined,
      })
    } catch (err) {
      appendMessage({ role: 'system', text: err instanceof Error ? err.message : 'Something went wrong.' })
    } finally {
      setSending(false)
    }
  }

  const handleConfirm = async (messageId: number, confirmationId: string) => {
    if (!token) return
    setConfirmingId(confirmationId)

    try {
      const result = await confirmAgentAction(token, confirmationId)
      setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, confirmationResolved: true } : m)))
      appendMessage({ role: 'system', text: result.response })
    } catch (err) {
      appendMessage({ role: 'system', text: err instanceof Error ? err.message : 'Could not confirm.' })
    } finally {
      setConfirmingId(null)
    }
  }

  const handleCancel = (messageId: number) => {
    setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, confirmationResolved: true } : m)))
    appendMessage({ role: 'system', text: 'Cancelled — no command was sent.' })
  }

  const handleNewConversation = async () => {
    setMessages([])
    if (token) {
      try {
        await resetAgentChat(token)
      } catch (err) {
        console.error('Failed to reset agent conversation', err)
      }
    }
  }

  return (
    <div className="agent-chat">
      <div className="agent-chat_header">
        <h3>Fleet Assistant</h3>
        {messages.length > 0 && (
          <button type="button" className="agent-chat_reset" onClick={handleNewConversation}>
            New conversation
          </button>
        )}
      </div>

      <div className="agent-chat_log" ref={logRef}>
        {messages.length === 0 && (
          <p className="agent-chat_empty">Ask about the fleet — e.g. "What robots need attention?"</p>
        )}

        {messages.map((m) => (
          <div key={m.id} className={`agent-chat_message agent-chat_message--${m.role}`}>
            <div className="agent-chat_bubble">
              {m.text}
              {m.toolCalls && m.toolCalls.length > 0 && (
                <div className="agent-chat_tools">
                  {m.toolCalls.map((tc, i) => (
                    <span key={i} className={`agent-chat_tool agent-chat_tool--${tc.status}`} title={tc.detail ?? undefined}>
                      {tc.tool}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {m.confirmationId && !m.confirmationResolved && (
              <div className="agent-chat_confirm">
                <button
                  type="button"
                  className="agent-chat_confirm-btn"
                  disabled={confirmingId === m.confirmationId}
                  onClick={() => handleConfirm(m.id, m.confirmationId as string)}
                >
                  {confirmingId === m.confirmationId ? 'Confirming…' : 'Confirm'}
                </button>
                <button type="button" className="agent-chat_cancel-btn" onClick={() => handleCancel(m.id)}>
                  Cancel
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      <form className="agent-chat_form" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about the fleet…"
          disabled={sending}
        />
        <button type="submit" disabled={sending || !input.trim()}>
          {sending ? '…' : 'Send'}
        </button>
      </form>
    </div>
  )
}
