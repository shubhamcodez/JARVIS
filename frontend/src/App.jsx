import { useState, useEffect, useRef, useCallback } from 'react'
import {
  listChats,
  setCurrentChat,
  getCurrentChatId,
  readChatLog,
  sendMessage,
  sendMessageStream,
  sendMessageWithFiles,
  appendChatLog,
  getChatsStoragePath,
  setChatsStoragePath,
  agentStepsWsUrl,
} from './api'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import './App.css'

const CHAT_ICON = (
  <svg className="chat-history-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
)

function escapeHtml(text) {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

function App() {
  const [panel, setPanel] = useState('chats')
  const [chats, setChats] = useState([])
  const [currentChatId, setCurrentChatIdState] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState([])
  const [storagePath, setStoragePath] = useState('')
  const [sending, setSending] = useState(false)
  const [liveReply, setLiveReply] = useState(null)
  const [agentLiveSteps, setAgentLiveSteps] = useState([])
  const wsRef = useRef(null)
  const messagesEndRef = useRef(null)
  const fileInputRef = useRef(null)

  const refreshChatList = useCallback(async () => {
    try {
      const list = await listChats()
      setChats(list)
    } catch {
      setChats([])
    }
  }, [])

  const refreshStoragePath = useCallback(async () => {
    try {
      const path = await getChatsStoragePath()
      setStoragePath(path || '')
    } catch {
      setStoragePath('')
    }
  }, [])

  const selectChat = useCallback(async (chatId) => {
    try {
      await setCurrentChat(chatId)
      setCurrentChatIdState(chatId)
      const msgs = await readChatLog(chatId)
      setMessages(msgs || [])
    } catch (e) {
      console.error(e)
    }
  }, [])

  useEffect(() => {
    refreshChatList()
    getCurrentChatId().then((id) => {
      setCurrentChatIdState(id)
      if (id) selectChat(id)
    })
  }, [refreshChatList, selectChat])

  useEffect(() => {
    if (panel === 'settings') refreshStoragePath()
  }, [panel, refreshStoragePath])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, agentLiveSteps])

  useEffect(() => {
    const url = agentStepsWsUrl()
    const ws = new WebSocket(url)
    ws.onmessage = (e) => {
      try {
        const p = JSON.parse(e.data)
        setAgentLiveSteps((prev) => [...prev, p])
      } catch {}
    }
    ws.onclose = () => {}
    wsRef.current = ws
    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [])

  const handleStorageChange = async () => {
    const path = prompt('Enter folder path for chat storage:', storagePath)
    if (path == null || path === '') return
    try {
      await setChatsStoragePath(path)
      setStoragePath(path)
      refreshChatList()
    } catch (err) {
      alert(err?.message || 'Could not change storage location.')
    }
  }

  const handleAttach = () => {
    fileInputRef.current?.click()
  }

  const onFileChange = (e) => {
    const files = Array.from(e.target.files || [])
    setAttachments((prev) => [...prev, ...files])
    e.target.value = ''
  }

  const removeAttachment = (index) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index))
  }

  const appendMessage = (text, isUser) => {
    setMessages((prev) => [...prev, { role: isUser ? 'user' : 'assistant', content: text }])
  }

  const handleSend = async () => {
    const raw = input.trim()
    if (!raw && attachments.length === 0) return
    setInput('')
    const filesToSend = [...attachments]
    setAttachments([])

    const displayText =
      raw ||
      (filesToSend.length === 1
        ? filesToSend[0].name
        : filesToSend.length > 1
          ? filesToSend.map((f) => f.name).join(', ')
          : '')
    appendMessage(displayText, true)
    setSending(true)
    setLiveReply('Working on it…')
    setAgentLiveSteps([])

    try {
      await appendChatLog('user', displayText)
    } catch {}

    try {
      let chatId = currentChatId
      if (!chatId) {
        chatId = (await getCurrentChatId()) || null
        setCurrentChatIdState(chatId)
      }
      let reply
      if (filesToSend.length > 0) {
        reply = await sendMessageWithFiles(
          raw || 'Please summarize or answer based on the attached documents.',
          filesToSend,
          chatId
        )
        appendMessage(reply, false)
        await appendChatLog('assistant', reply)
      } else {
        reply = await sendMessageStream(
          raw || 'Please summarize or answer based on the attached documents.',
          null,
          chatId,
          { onChunk: (delta) => setLiveReply((prev) => (prev || '') + delta) }
        )
        appendMessage(reply || '', false)
        await appendChatLog('assistant', reply || '')
      }
      setLiveReply(null)
      setAgentLiveSteps([])
    } catch (err) {
      setLiveReply(null)
      setAgentLiveSteps([])
      const msg = err?.message || 'Sorry, something went wrong. Please try again.'
      appendMessage(msg, false)
      try {
        await appendChatLog('assistant', msg)
      } catch {}
    }
    setSending(false)
    refreshChatList()
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="app">
      <header className="titlebar">
        <div className="titlebar-brand">
          <img src="/JARVIS.jpg" alt="" className="titlebar-logo" />
          <span className="titlebar-title">JARVIS</span>
        </div>
      </header>
      <div className="app-body">
        <aside className="sidebar">
          <div className="sidebar-tabs" role="tablist">
            <button
              type="button"
              className={`sidebar-tab ${panel === 'chats' ? 'active' : ''}`}
              onClick={() => setPanel('chats')}
              aria-selected={panel === 'chats'}
            >
              Chats
            </button>
            <button
              type="button"
              className={`sidebar-tab ${panel === 'activity' ? 'active' : ''}`}
              onClick={() => setPanel('activity')}
              aria-selected={panel === 'activity'}
            >
              Activity
            </button>
            <button
              type="button"
              className={`sidebar-tab ${panel === 'settings' ? 'active' : ''}`}
              onClick={() => setPanel('settings')}
              aria-selected={panel === 'settings'}
            >
              Settings
            </button>
          </div>
          <div className="sidebar-panel" style={{ display: panel === 'chats' ? 'flex' : 'none' }}>
            <div className="sidebar-list chat-history-list">
              {chats.length === 0 ? (
                <p className="chat-history-empty">No conversations yet. Start chatting to see them here.</p>
              ) : (
                chats.map((chat) => (
                  <button
                    key={chat.id}
                    type="button"
                    className={`chat-history-item ${currentChatId === chat.id ? 'active' : ''}`}
                    onClick={() => selectChat(chat.id)}
                  >
                    {CHAT_ICON}
                    <span className="chat-history-title" title={escapeHtml(chat.title)}>
                      {chat.title}
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>
          <div className="sidebar-panel" style={{ display: panel === 'activity' ? 'flex' : 'none' }}>
            <div className="sidebar-list activity-list">
              <p className="activity-empty">No actions yet. Actions the chatbot takes will appear here.</p>
            </div>
          </div>
          <div className="sidebar-panel" style={{ display: panel === 'settings' ? 'flex' : 'none' }}>
            <div className="sidebar-list settings-panel">
              <div className="settings-section">
                <label className="settings-label">Storage location</label>
                <p className="settings-description">Where chat logs are saved.</p>
                <div className="settings-storage-row">
                  <input
                    type="text"
                    readOnly
                    className="settings-storage-input"
                    value={storagePath}
                    aria-label="Chats storage path"
                  />
                  <button type="button" className="settings-storage-btn" onClick={handleStorageChange}>
                    Change
                  </button>
                </div>
              </div>
            </div>
          </div>
        </aside>
        <div className="chat-container">
          <div className="chat-messages">
            {messages.map((msg, i) => (
              <div key={i} className={`msg ${msg.role === 'user' ? 'msg-user' : 'msg-bot'}`}>
                {msg.role === 'user' ? (
                  <span className="msg-text">{msg.content}</span>
                ) : (
                  <div className="msg-markdown">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  </div>
                )}
              </div>
            ))}
            {liveReply && (
              <div className="msg msg-bot">
                <div className="msg-markdown">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{liveReply}</ReactMarkdown>
                </div>
                <div className="agent-thought-process">
                  {agentLiveSteps.map((s, i) => (
                    <div key={i} className={`agent-step ${s.step === 0 ? 'agent-step-supervisor' : ''}`}>
                      <strong>{s.step === 0 ? 'Supervisor' : `Step ${s.step}`}</strong> — {s.thought || ''}
                      <br />
                      <em>Action: {s.description || s.action || ''}</em>
                      {s.result && (
                        <>
                          <br />→ {s.result}
                        </>
                      )}
                      {s.screenshot && (
                        <div className="agent-step-screenshot-wrap">
                          <img
                            src={`data:image/png;base64,${s.screenshot}`}
                            alt={`Step ${s.step} screenshot`}
                            className="agent-step-screenshot"
                          />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
          <div className="chat-input-area">
            {attachments.length > 0 && (
              <div className="chat-attachments">
                {attachments.map((f, i) => (
                  <span key={i} className="chat-attachment">
                    <span className="chat-attachment-name" title={f.name}>
                      {f.name}
                    </span>
                    <button
                      type="button"
                      className="chat-attachment-remove"
                      aria-label="Remove"
                      onClick={() => removeAttachment(i)}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className="chat-input-row">
              <button
                type="button"
                id="chat-attach"
                className="chat-attach-btn"
                aria-label="Attach files"
                onClick={handleAttach}
              >
                📎
              </button>
              <input type="file" ref={fileInputRef} style={{ display: 'none' }} multiple onChange={onFileChange} />
              <textarea
                id="chat-input"
                placeholder="Message JARVIS..."
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={sending}
              />
              <button type="button" id="chat-send" onClick={handleSend} disabled={sending}>
                Send
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
