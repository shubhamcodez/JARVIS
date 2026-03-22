const API_BASE = import.meta.env.VITE_API_URL || '/api';

async function request(path, options = {}) {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  });
  if (!res.ok) {
    const text = await res.text();
    // Vite proxy returns 502 when nothing listens on localhost:8000
    if (res.status === 502) {
      throw new Error(
        'Cannot reach the API. Start the backend from the repo: cd backend && poetry run uvicorn main:app --reload --port 8000'
      );
    }
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
 * onStatus({ phase, message, ... }) for supervisor / context / agent progress.
 * onAgentStep({ step, thought, action, description, result, done }) for each agent step (SSE omits screenshot; UI merges WS payloads into the same timeline row).
 * If the backend used a tool, calls onToolUsed(toolUsed) and returns { reply, tool_used }.
 */
export async function sendMessageStream(
  message,
  attachmentPaths,
  chatId,
  { onChunk, onDone, onToolUsed, onStatus, onAgentStep }
) {
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
  let toolUsed = null
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
          if (data.type === 'status') {
            onStatus?.(data)
            continue
          }
          if (data.type === 'agent_step') {
            onAgentStep?.(data)
            continue
          }
          if (data.delta != null) {
            full += data.delta
            onChunk?.(data.delta)
          }
          if (data.done && data.reply != null) {
            full = data.reply
            if (data.tool_used) {
              toolUsed = data.tool_used
              onToolUsed?.(data.tool_used)
            }
            onDone?.(data.reply)
            return { reply: data.reply, tool_used: data.tool_used ?? null }
          }
        } catch (_) {}
      }
    }
  }
  if (full) onDone?.(full)
  return { reply: full, tool_used: toolUsed }
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

/** Create a new empty chat and set it as current. Returns the new chat_id. */
export async function createNewChat() {
  const { chat_id } = await request('/chat/new', { method: 'POST' });
  return chat_id;
}

/** Delete a chat by id. Returns { ok, deleted }. */
export async function deleteChat(chatId) {
  return request(`/chat/${encodeURIComponent(chatId)}`, { method: 'DELETE' });
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

/** Current LLM provider: "openai" (GPT) or "xai" (Grok). */
export async function getModelSetting() {
  const { provider } = await request('/settings/model');
  return provider || 'openai';
}

export async function setModelSetting(provider) {
  await request('/settings/model', {
    method: 'POST',
    body: JSON.stringify({ provider: provider === 'xai' ? 'xai' : 'openai' }),
  });
  return provider;
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
