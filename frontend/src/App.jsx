import { useState, useEffect, useRef, useCallback } from 'react'
import {
  listChats,
  setCurrentChat,
  getCurrentChatId,
  readChatLog,
  createNewChat,
  deleteChat,
  sendMessage,
  sendMessageStream,
  sendMessageWithFiles,
  appendChatLog,
  getChatsStoragePath,
  setChatsStoragePath,
  getModelSetting,
  setModelSetting,
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

const COPY_ICON = (
  <svg className="msg-copy-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
  </svg>
)

function CopyResponseButton({ text }) {
  const [copied, setCopied] = useState(false)
  const plain = typeof text === 'string' ? text : String(text ?? '')
  const handleCopy = async () => {
    if (!plain.trim()) return
    try {
      await navigator.clipboard.writeText(plain)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      try {
        const ta = document.createElement('textarea')
        ta.value = plain
        ta.setAttribute('readonly', '')
        ta.style.position = 'fixed'
        ta.style.left = '-9999px'
        document.body.appendChild(ta)
        ta.select()
        document.execCommand('copy')
        document.body.removeChild(ta)
        setCopied(true)
        window.setTimeout(() => setCopied(false), 2000)
      } catch {
        /* ignore */
      }
    }
  }
  return (
    <div className="msg-copy-row">
      <button
        type="button"
        className={`msg-copy-btn${copied ? ' msg-copy-btn--done' : ''}`}
        onClick={handleCopy}
        disabled={!plain.trim()}
        aria-label={copied ? 'Copied to clipboard' : 'Copy response to clipboard'}
      >
        {COPY_ICON}
        <span>{copied ? 'Copied' : 'Copy'}</span>
      </button>
    </div>
  )
}

function App() {
  const [panel, setPanel] = useState('chats')
  const [chats, setChats] = useState([])
  const [currentChatId, setCurrentChatIdState] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState([])
  const [storagePath, setStoragePath] = useState('')
  const [modelProvider, setModelProvider] = useState('openai')
  const [sending, setSending] = useState(false)
  const [liveReply, setLiveReply] = useState(null)
  const [streamTimeline, setStreamTimeline] = useState([])
  /** Screenshots arrive on WebSocket; SSE step may arrive first or second — stash by step id */
  const screenshotPendingRef = useRef({})
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

  const refreshModelSetting = useCallback(async () => {
    try {
      const provider = await getModelSetting()
      setModelProvider(provider || 'openai')
    } catch {
      setModelProvider('openai')
    }
  }, [])

  const refreshSettings = useCallback(async () => {
    await refreshStoragePath()
    await refreshModelSetting()
  }, [refreshStoragePath, refreshModelSetting])

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
    getCurrentChatId()
      .then((id) => {
        setCurrentChatIdState(id)
        if (id) selectChat(id)
      })
      .catch(() => {
        setCurrentChatIdState(null)
      })
  }, [refreshChatList, selectChat])

  useEffect(() => {
    if (panel === 'settings') refreshSettings()
  }, [panel, refreshSettings])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamTimeline])

  useEffect(() => {
    const url = agentStepsWsUrl()
    const ws = new WebSocket(url)
    ws.onmessage = (e) => {
      try {
        const p = JSON.parse(e.data)
        if (p.screenshot == null || p.screenshot === '') return
        const step = p.step
        setStreamTimeline((prev) => {
          const i = prev.findIndex((x) => x.kind === 'step' && x.step === step)
          if (i >= 0) {
            const next = [...prev]
            next[i] = { ...next[i], screenshot: p.screenshot }
            return next
          }
          screenshotPendingRef.current[step] = p.screenshot
          return prev
        })
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

  const handleModelChange = async (e) => {
    const provider = e.target.value
    if (provider !== 'openai' && provider !== 'xai') return
    try {
      await setModelSetting(provider)
      setModelProvider(provider)
    } catch (err) {
      alert(err?.message || 'Could not save model setting.')
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

  const appendToolMessage = (toolUsed) => {
    setMessages((prev) => [...prev, { role: 'tool', content: JSON.stringify(toolUsed) }])
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
    setLiveReply('')
    setStreamTimeline([])
    screenshotPendingRef.current = {}

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
        const formatAgentStep = (d) => {
          const n = d.step
          const thought = (d.thought || '').trim()
          const desc = (d.description || '').trim()
          const res = d.result != null ? String(d.result).trim() : ''
          const lower = `${desc} ${thought}`.toLowerCase()
          const retry = lower.includes('retry') || lower.includes('trying again')
          if (n === 0) {
            return {
              kind: 'step',
              phase: 'plan',
              message: 'Forming a plan',
              detail: desc || thought,
              step: 0,
              screenshot: d.screenshot || null,
            }
          }
          let message = `Implementing step ${n}: ${d.action || 'action'}`
          if (retry) message = `Step ${n} failed — trying again`
          const detail = [desc || thought, res ? `→ ${res}` : ''].filter(Boolean).join(' ').slice(0, 600)
          return {
            kind: 'step',
            phase: 'run',
            message,
            detail,
            step: n,
            screenshot: d.screenshot || null,
          }
        }

        const streamResult = await sendMessageStream(
          raw || 'Please summarize or answer based on the attached documents.',
          null,
          chatId,
          {
            onChunk: (delta) => setLiveReply((prev) => (prev || '') + delta),
            onStatus: (d) => {
              if (d.phase === 'done') return
              setStreamTimeline((prev) => [
                ...prev,
                {
                  kind: 'status',
                  phase: d.phase,
                  message: d.message || d.phase,
                  detail:
                    d.next_steps ||
                    d.reasoning ||
                    (d.goal && d.phase === 'supervisor_done' ? `Goal: ${d.goal}` : '') ||
                    '',
                },
              ])
            },
            onAgentStep: (d) => {
              const row = formatAgentStep(d)
              const pending = screenshotPendingRef.current[d.step]
              if (pending != null) {
                delete screenshotPendingRef.current[d.step]
              }
              const screenshot = d.screenshot || pending || row.screenshot || null
              setStreamTimeline((prev) => [...prev, { ...row, screenshot }])
            },
          }
        )
        reply = streamResult?.reply ?? streamResult ?? ''
        if (streamResult?.tool_used) appendToolMessage(streamResult.tool_used)
        appendMessage(reply || '', false)
        await appendChatLog('assistant', reply || '')
      }
      setLiveReply(null)
      setStreamTimeline([])
    } catch (err) {
      setLiveReply(null)
      setStreamTimeline([])
      screenshotPendingRef.current = {}
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
            <button
              type="button"
              className="chat-new-btn"
              onClick={async () => {
                try {
                  const chatId = await createNewChat()
                  setCurrentChatIdState(chatId)
                  setMessages([])
                  await refreshChatList()
                } catch (e) {
                  console.error(e)
                }
              }}
            >
              + New chat
            </button>
            <div className="sidebar-list chat-history-list">
              {chats.length === 0 ? (
                <p className="chat-history-empty">No conversations yet. Start chatting to see them here.</p>
              ) : (
                chats.map((chat) => (
                  <div
                    key={chat.id}
                    className={`chat-history-item-wrap ${currentChatId === chat.id ? 'active' : ''}`}
                  >
                    <button
                      type="button"
                      className="chat-history-item"
                      onClick={() => selectChat(chat.id)}
                    >
                      {CHAT_ICON}
                      <span className="chat-history-title" title={escapeHtml(chat.title)}>
                        {chat.title}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="chat-history-delete"
                      aria-label="Delete chat"
                      onClick={async (e) => {
                        e.stopPropagation()
                        if (!confirm('Delete this chat?')) return
                        try {
                          await deleteChat(chat.id)
                          if (currentChatId === chat.id) {
                            setCurrentChatIdState(null)
                            setMessages([])
                          }
                          await refreshChatList()
                        } catch (err) {
                          console.error(err)
                          alert(err?.message || 'Could not delete chat.')
                        }
                      }}
                    >
                      ×
                    </button>
                  </div>
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
              <div className="settings-section">
                <label className="settings-label">Model</label>
                <p className="settings-description">LLM used for chat and agents.</p>
                <select
                  className="settings-model-select"
                  value={modelProvider}
                  onChange={handleModelChange}
                  aria-label="Model provider"
                >
                  <option value="openai">OpenAI (GPT-4o)</option>
                  <option value="xai">xAI (Grok)</option>
                </select>
              </div>
            </div>
          </div>
        </aside>
        <div className="chat-container">
          <div className="chat-messages">
            {messages.map((msg, i) => (
              <div key={i} className={`msg ${msg.role === 'user' ? 'msg-user' : msg.role === 'tool' ? 'msg-tool' : 'msg-bot'}`}>
                {msg.role === 'user' ? (
                  <span className="msg-text">{msg.content}</span>
                ) : msg.role === 'tool' ? (
                  (() => {
                    try {
                      const t = typeof msg.content === 'string' ? JSON.parse(msg.content) : msg.content
                      const name = t?.name || 'tool'
                      const input = t?.input ?? ''
                      const result = t?.result ?? ''
                      return (
                        <div className="msg-tool-card">
                          <span className="msg-tool-label">
                            🔧 {name}{input ? ` (${input})` : ''}
                          </span>
                          <div className="msg-tool-result">{result}</div>
                        </div>
                      )
                    } catch {
                      return <span className="msg-text">{msg.content}</span>
                    }
                  })()
                ) : (
                  <div className="msg-bot-body">
                    <div className="msg-markdown">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                    </div>
                    <CopyResponseButton text={msg.content} />
                  </div>
                )}
              </div>
            ))}
            {(sending || liveReply || streamTimeline.length > 0) && (
              <div className="msg msg-bot msg-streaming">
                {streamTimeline.length > 0 && (
                  <div className="stream-timeline" aria-live="polite">
                    {streamTimeline.map((item, i) => (
                      <div
                        key={i}
                        className={`stream-timeline-row stream-timeline-${item.kind} stream-phase-${item.phase || ''}${item.screenshot ? ' stream-timeline-has-screenshot' : ''}`}
                      >
                        <span className="stream-timeline-dot" aria-hidden />
                        <div className="stream-timeline-body">
                          <div className="stream-timeline-title">{item.message}</div>
                          {item.detail ? (
                            <div className="stream-timeline-detail">{item.detail}</div>
                          ) : null}
                          {item.screenshot ? (
                            <div className="stream-timeline-screenshot-wrap">
                              <img
                                src={`data:image/png;base64,${item.screenshot}`}
                                alt={`Step ${item.step ?? i} screenshot`}
                                className="stream-timeline-screenshot"
                                loading="lazy"
                              />
                              <span className="stream-timeline-screenshot-label">Screenshot used for this step</span>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {liveReply ? (
                  <div className="msg-bot-body msg-stream-reply-body">
                    <div className="msg-markdown stream-reply-md">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{liveReply}</ReactMarkdown>
                    </div>
                    <CopyResponseButton text={liveReply} />
                  </div>
                ) : null}
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
