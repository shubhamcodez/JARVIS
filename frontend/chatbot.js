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

// Sidebar tabs: Chats | Agent | Activity | Settings
const tabChats = document.getElementById("tab-chats");
const tabAgent = document.getElementById("tab-agent");
const tabActivity = document.getElementById("tab-activity");
const tabSettings = document.getElementById("tab-settings");
const panelChats = document.getElementById("panel-chats");
const panelAgent = document.getElementById("panel-agent");
const panelActivity = document.getElementById("panel-activity");
const panelSettings = document.getElementById("panel-settings");

function showPanel(panel) {
  panelChats.classList.toggle("active", panel === "chats");
  panelAgent.classList.toggle("active", panel === "agent");
  panelActivity.classList.toggle("active", panel === "activity");
  panelSettings.classList.toggle("active", panel === "settings");
  panelChats.hidden = panel !== "chats";
  panelAgent.hidden = panel !== "agent";
  panelActivity.hidden = panel !== "activity";
  panelSettings.hidden = panel !== "settings";
  tabChats.classList.toggle("active", panel === "chats");
  tabAgent.classList.toggle("active", panel === "agent");
  tabActivity.classList.toggle("active", panel === "activity");
  tabSettings.classList.toggle("active", panel === "settings");
  tabChats.setAttribute("aria-selected", panel === "chats");
  tabAgent.setAttribute("aria-selected", panel === "agent");
  tabActivity.setAttribute("aria-selected", panel === "activity");
  tabSettings.setAttribute("aria-selected", panel === "settings");
}

tabChats.addEventListener("click", () => {
  showPanel("chats");
  refreshChatHistory();
});

tabAgent.addEventListener("click", () => {
  showPanel("agent");
  refreshAgentSessions();
});

tabActivity.addEventListener("click", () => showPanel("activity"));
tabSettings.addEventListener("click", () => {
  showPanel("settings");
  refreshSettingsStoragePath();
});

// Agent tab: submit goal, list sessions, show session detail
const agentGoalInput = document.getElementById("agent-goal-input");
const agentSubmitGoalBtn = document.getElementById("agent-submit-goal");
const agentSessionList = document.getElementById("agent-session-list");
const agentDetail = document.getElementById("agent-detail");
const agentSubgoals = document.getElementById("agent-subgoals");
const agentTrace = document.getElementById("agent-trace");

async function refreshAgentSessions() {
  try {
    const ids = await invoke("agent_list_sessions");
    agentSessionList.innerHTML = "";
    if (!ids || ids.length === 0) {
      agentSessionList.innerHTML = '<p class="agent-empty">No agent sessions yet. Submit a goal above.</p>';
      return;
    }
    for (const id of ids) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chat-history-item";
      btn.setAttribute("data-agent-id", id);
      btn.textContent = id;
      btn.addEventListener("click", () => showAgentSession(id));
      agentSessionList.appendChild(btn);
    }
  } catch (_) {
    agentSessionList.innerHTML = '<p class="agent-empty">No agent sessions.</p>';
  }
}

let selectedAgentSessionId = null;

const agentApprovalModal = document.getElementById("agent-approval-modal");
const agentApprovalDescription = document.getElementById("agent-approval-description");
const agentApproveBtn = document.getElementById("agent-approve-btn");
const agentRejectBtn = document.getElementById("agent-reject-btn");

async function showAgentSession(id) {
  selectedAgentSessionId = id;
  try {
    const session = await invoke("agent_get_session", { id });
    agentDetail.hidden = false;
    agentSubgoals.innerHTML = "";
    for (let i = 0; i < session.subgoals.length; i++) {
      const li = document.createElement("li");
      li.textContent = `${i + 1}. ${session.subgoals[i]}`;
      agentSubgoals.appendChild(li);
    }
    const isBlocked = session.status === "blocked" && session.blocked_reason === "awaiting_approval";
    agentApprovalModal.hidden = !isBlocked;
    if (isBlocked) {
      agentApprovalDescription.textContent = session.pending_action_description || "Action pending approval.";
    }
    agentTrace.textContent = session.trace_lines.length ? session.trace_lines.join("\n") : "(no trace yet)";
  } catch (_) {
    agentDetail.hidden = true;
  }
}

async function submitAgentApproval(approved) {
  if (!selectedAgentSessionId) return;
  try {
    const summary = await invoke("agent_approve_action", { sessionId: selectedAgentSessionId, approved });
    showAgentSession(summary.id);
  } catch (err) {
    console.error(err && (err.message || err));
  }
}

agentApproveBtn.addEventListener("click", () => submitAgentApproval(true));
agentRejectBtn.addEventListener("click", () => submitAgentApproval(false));

const agentRunStepBtn = document.getElementById("agent-run-step");
agentRunStepBtn.addEventListener("click", async () => {
  if (!selectedAgentSessionId) return;
  agentRunStepBtn.disabled = true;
  try {
    const summary = await invoke("agent_run_step", { sessionId: selectedAgentSessionId });
    showAgentSession(summary.id);
  } catch (err) {
    console.error(err && (err.message || err));
  }
  agentRunStepBtn.disabled = false;
});

agentSubmitGoalBtn.addEventListener("click", async () => {
  const goal = agentGoalInput.value.trim();
  if (!goal) return;
  agentSubmitGoalBtn.disabled = true;
  try {
    const summary = await invoke("agent_submit_goal", { goal });
    agentGoalInput.value = "";
    refreshAgentSessions();
    showAgentSession(summary.id);
  } catch (err) {
    const msg = (err && (err.message || err)) || "Failed to submit goal.";
    console.error(msg);
  }
  agentSubmitGoalBtn.disabled = false;
});

// Settings: storage location
const settingsStoragePathInput = document.getElementById("settings-storage-path");
const settingsStorageChangeBtn = document.getElementById("settings-storage-change");

async function refreshSettingsStoragePath() {
  try {
    const path = await invoke("get_chats_storage_path");
    settingsStoragePathInput.value = path || "";
  } catch (_) {
    settingsStoragePathInput.value = "";
  }
}

settingsStorageChangeBtn.addEventListener("click", async () => {
  try {
    const selected = await invoke("open_folder_picker");
    if (selected != null && selected !== "") {
      await invoke("set_chats_storage_path", { path: selected });
      settingsStoragePathInput.value = selected;
      refreshChatHistory();
    }
  } catch (err) {
    const msg = (err && (err.message || err)) || "Could not change storage location.";
    console.error(msg);
  }
});

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
  const displayText = raw || (pathsToSend.length
    ? (pathsToSend.length === 1
      ? `${basename(pathsToSend[0])} has been read`
      : `${pathsToSend.map(basename).join(", ")} have been read`)
    : "");
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
