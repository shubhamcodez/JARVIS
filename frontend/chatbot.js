const chatMessages = document.getElementById("chat-messages");
const chatInput = document.getElementById("chat-input");
const chatSend = document.getElementById("chat-send");
const chatAttach = document.getElementById("chat-attach");
const chatAttachments = document.getElementById("chat-attachments");

const invoke = window.__TAURI__.core.invoke;

let attachmentPaths = [];

document.getElementById("titlebar-minimize").addEventListener("click", () => invoke("window_minimize"));
document.getElementById("titlebar-close").addEventListener("click", () => invoke("window_close"));
document.getElementById("titlebar-maximize").addEventListener("click", () => invoke("window_toggle_maximize"));

// Sidebar tabs: Chats | Activity
const tabChats = document.getElementById("tab-chats");
const tabActivity = document.getElementById("tab-activity");
const panelChats = document.getElementById("panel-chats");
const panelActivity = document.getElementById("panel-activity");

function showPanel(panel) {
  panelChats.classList.toggle("active", panel === "chats");
  panelActivity.classList.toggle("active", panel === "activity");
  panelChats.hidden = panel !== "chats";
  panelActivity.hidden = panel !== "activity";
  tabChats.classList.toggle("active", panel === "chats");
  tabActivity.classList.toggle("active", panel === "activity");
  tabChats.setAttribute("aria-selected", panel === "chats");
  tabActivity.setAttribute("aria-selected", panel === "activity");
}

tabChats.addEventListener("click", () => {
  showPanel("chats");
  refreshChatHistory();
});

tabActivity.addEventListener("click", () => showPanel("activity"));

// Chat history: list from backend, ChatGPT-style titles
const chatHistoryList = document.getElementById("chat-history-list");

const chatIconSvg = `<svg class="chat-history-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`;

async function refreshChatHistory() {
  try {
    const chats = await invoke("list_chats");
    chatHistoryList.innerHTML = "";
    if (!chats || chats.length === 0) {
      const empty = document.createElement("p");
      empty.className = "chat-history-empty";
      empty.textContent = "No conversations yet. Start chatting to see them here.";
      chatHistoryList.appendChild(empty);
      return;
    }
    for (const chat of chats) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chat-history-item";
      btn.setAttribute("data-chat-id", chat.id);
      btn.innerHTML = chatIconSvg + `<span class="chat-history-title">${escapeHtml(chat.title)}</span>`;
      chatHistoryList.appendChild(btn);
    }
  } catch (_) {
    chatHistoryList.innerHTML = "";
    const empty = document.createElement("p");
    empty.className = "chat-history-empty";
    empty.textContent = "No conversations yet.";
    chatHistoryList.appendChild(empty);
  }
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

refreshChatHistory();

function basename(path) {
  return path.replace(/^.*[/\\]/, "") || path;
}

function renderAttachments() {
  chatAttachments.innerHTML = "";
  if (attachmentPaths.length === 0) {
    chatAttachments.hidden = true;
    return;
  }
  chatAttachments.hidden = false;
  for (let i = 0; i < attachmentPaths.length; i++) {
    const path = attachmentPaths[i];
    const name = basename(path);
    const chip = document.createElement("span");
    chip.className = "chat-attachment";
    chip.innerHTML = `<span class="chat-attachment-name" title="${escapeHtml(path)}">${escapeHtml(name)}</span><button type="button" class="chat-attachment-remove" aria-label="Remove" data-index="${i}">×</button>`;
    chip.querySelector(".chat-attachment-remove").addEventListener("click", () => {
      attachmentPaths.splice(i, 1);
      renderAttachments();
    });
    chatAttachments.appendChild(chip);
  }
}

chatAttach.addEventListener("click", async () => {
  try {
    const paths = await invoke("open_file_picker");
    if (paths && paths.length) {
      attachmentPaths.push(...paths);
      renderAttachments();
    }
  } catch (_) {}
});

function appendMessage(text, isUser) {
  const div = document.createElement("div");
  div.className = isUser ? "msg msg-user" : "msg msg-bot";
  const span = document.createElement("span");
  span.className = "msg-text";
  span.textContent = text;
  div.appendChild(span);
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendMessage() {
  const raw = chatInput.value.trim();
  if (!raw && attachmentPaths.length === 0) return;
  chatInput.value = "";
  const pathsToSend = attachmentPaths.slice();
  attachmentPaths = [];
  renderAttachments();
  const displayText = raw || "(attached documents)";
  appendMessage(displayText, true);
  chatSend.disabled = true;

  try {
    await invoke("append_chat_log", { role: "user", content: displayText });
  } catch (_) {}

  try {
    const reply = await invoke("chatbot_response", {
      message: raw || "Please summarize or answer based on the attached documents.",
      attachmentPaths: pathsToSend.length ? pathsToSend : null,
    });
    appendMessage(reply, false);
    await invoke("append_chat_log", { role: "assistant", content: reply });
  } catch (err) {
    const msg = (err && (err.message || err)) || "Sorry, something went wrong. Please try again.";
    appendMessage(String(msg), false);
    try {
      await invoke("append_chat_log", { role: "assistant", content: msg });
    } catch (_) {}
  }
  chatSend.disabled = false;
  refreshChatHistory();
}

chatSend.addEventListener("click", sendMessage);
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
