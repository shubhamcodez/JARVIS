const API_BASE = import.meta.env.VITE_API_URL || '/api';

async function request(path, options = {}) {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function chatbotResponse(message, attachmentPaths = null) {
  const { reply } = await request('/chat/response', {
    method: 'POST',
    body: JSON.stringify({ message: message || '', attachment_paths: attachmentPaths }),
  });
  return reply;
}

export async function sendMessage(message, attachmentPaths = null, chatId = null) {
  const { reply } = await request('/chat/send-message', {
    method: 'POST',
    body: JSON.stringify({
      message: message || '',
      attachment_paths: attachmentPaths,
      chat_id: chatId,
    }),
  });
  return reply;
}

/**
 * Stream send-message: calls onChunk(delta) as tokens arrive, then onDone(fullReply).
 * Uses SSE endpoint /chat/send-message/stream.
 */
export async function sendMessageStream(message, attachmentPaths, chatId, { onChunk, onDone }) {
  const base = import.meta.env.VITE_API_URL || '/api'
  const res = await fetch(base + '/chat/send-message/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: message || '',
      attachment_paths: attachmentPaths || null,
      chat_id: chatId || null,
    }),
  })
  if (!res.ok) throw new Error(await res.text() || `HTTP ${res.status}`)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let full = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6))
          if (data.delta != null) {
            full += data.delta
            onChunk?.(data.delta)
          }
          if (data.done && data.reply != null) {
            full = data.reply
            onDone?.(data.reply)
            return data.reply
          }
        } catch (_) {}
      }
    }
  }
  if (full) onDone?.(full)
  return full
}

/** Send message with file uploads (multipart). Use when user attached files. */
export async function sendMessageWithFiles(message, files = [], chatId = null) {
  const form = new FormData();
  form.append('message', message || '');
  form.append('chat_id', chatId ?? '');
  for (const f of files) {
    form.append('files', f);
  }
  const base = import.meta.env.VITE_API_URL || '/api';
  const url = base + '/chat/send-message-with-files';
  const res = await fetch(url, { method: 'POST', body: form });
  if (!res.ok) throw new Error(await res.text() || `HTTP ${res.status}`);
  const data = await res.json();
  return data.reply;
}

export async function appendChatLog(role, content) {
  await request('/chat/append', {
    method: 'POST',
    body: JSON.stringify({ role, content }),
  });
}

export async function listChats() {
  return request('/chat/list');
}

export async function setCurrentChat(chatId) {
  await request('/chat/set-current', {
    method: 'POST',
    body: JSON.stringify({ chat_id: chatId }),
  });
}

export async function getCurrentChatId() {
  const { chat_id } = await request('/chat/current-id');
  return chat_id;
}

export async function readChatLog(chatId) {
  return request(`/chat/read/${chatId}`);
}

export async function getChatsStoragePath() {
  const { path } = await request('/storage/chats-path');
  return path || '';
}

export async function setChatsStoragePath(path) {
  await request('/storage/chats-path', {
    method: 'POST',
    body: JSON.stringify({ path }),
  });
}

/** WebSocket URL for agent steps (use wsOrigin for WS) */
export function agentStepsWsUrl() {
  const base = import.meta.env.VITE_API_URL || '';
  if (base.startsWith('http://')) {
    return base.replace('http://', 'ws://') + '/ws/agent-steps';
  }
  if (base.startsWith('https://')) {
    return base.replace('https://', 'wss://') + '/ws/agent-steps';
  }
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  return `${proto}//${host}/ws/agent-steps`;
}
