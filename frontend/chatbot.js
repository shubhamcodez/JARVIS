const chatMessages = document.getElementById("chat-messages");
const chatInput = document.getElementById("chat-input");
const chatSend = document.getElementById("chat-send");

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
  if (!raw) return;
  chatInput.value = "";
  appendMessage(raw, true);
  chatSend.disabled = true;
  try {
    const reply = await window.__TAURI__.core.invoke("chatbot_response", { message: raw });
    appendMessage(reply, false);
  } catch (err) {
    const msg = (err && (err.message || err)) || "Sorry, something went wrong. Please try again.";
    appendMessage(String(msg), false);
  }
  chatSend.disabled = false;
}

chatSend.addEventListener("click", sendMessage);
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
