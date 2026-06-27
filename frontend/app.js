/**
 * app.js — Handa Aesthetics and Plastics AI Receptionist
 * Loaded as an ES Module. Imports VAPI SDK directly via ESM CDN.
 */
import VapiSDK from "https://cdn.jsdelivr.net/npm/@vapi-ai/web@latest/+esm";
// ESM CDN sometimes wraps the class under .default
const Vapi = (typeof VapiSDK === "function") ? VapiSDK : (VapiSDK.default ?? VapiSDK);

const API_BASE = "";

// ── State ─────────────────────────────────────────────────────────────────
let vapiInstance = null;
let assistantId  = null;
let callActive   = false;
let transcript   = [];

// ── DOM refs ──────────────────────────────────────────────────────────────
const callBtn           = document.getElementById("callButton");
const callLabel         = document.getElementById("callLabel");
const phoneIcon         = document.getElementById("phoneIcon");
const endIcon           = document.getElementById("endIcon");
const callHint          = document.getElementById("callHint");
const callStatusCtr     = document.getElementById("callStatusContainer");
const callRingOuter     = document.getElementById("callRingOuter");
const callRingInner     = document.getElementById("callRingInner");
const statusDot         = document.getElementById("statusDot");
const statusText        = document.getElementById("statusText");
const transcriptSection = document.getElementById("transcriptSection");
const transcriptBox     = document.getElementById("transcriptBox");
const clearBtn          = document.getElementById("clearTranscript");
const visualWave        = document.getElementById("visualWave");
const uploadZone        = document.getElementById("uploadZone");
const fileInput         = document.getElementById("fileInput");
const uploadStatus      = document.getElementById("uploadStatus");
const queryInput        = document.getElementById("queryInput");
const queryBtn          = document.getElementById("queryBtn");
const queryResult       = document.getElementById("queryResult");

// ── Helpers ───────────────────────────────────────────────────────────────
const sleep    = ms  => new Promise(r => setTimeout(r, ms));
const escHtml  = str => String(str)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;")
  .replace(/>/g,"&gt;").replace(/"/g,"&quot;");

// ── Simple markdown → HTML for bubbles ────────────────────────────
function renderMarkdown(text) {
  if (!text) return "";
  let html = escHtml(text);
  
  // Bold: **text** or __text__
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/__(.*?)__/g, '<strong>$1</strong>');
  
  // Italic: *text* or _text_
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
  html = html.replace(/_(.*?)_/g, '<em>$1</em>');
  
  // Parse bullet point lists line by line
  const lines = html.split('\n');
  let inList = false;
  const processedLines = [];
  
  for (let line of lines) {
    const trimmed = line.trim();
    const listMatch = trimmed.match(/^[\-\*]\s+(.*)$/);
    if (listMatch) {
      if (!inList) {
        processedLines.push('<ul>');
        inList = true;
      }
      processedLines.push(`<li>${listMatch[1]}</li>`);
    } else {
      if (inList) {
        processedLines.push('</ul>');
        inList = false;
      }
      processedLines.push(line);
    }
  }
  if (inList) {
    processedLines.push('</ul>');
  }
  
  // Join lines with proper block-level spacing (avoiding nested list <br>s)
  let finalHtml = '';
  for (let i = 0; i < processedLines.length; i++) {
    const current = processedLines[i];
    const trimmed = current.trim();
    finalHtml += current;
    
    if (i < processedLines.length - 1) {
      const next = processedLines[i + 1].trim();
      const currentIsListTag = trimmed === '<ul>' || trimmed === '</ul>' || trimmed.startsWith('<li>');
      const nextIsListTag = next === '<ul>' || next === '</ul>' || next.startsWith('<li>');
      
      if (!currentIsListTag || !nextIsListTag) {
        finalHtml += '<br>';
      } else {
        finalHtml += '\n';
      }
    }
  }
  return finalHtml;
}

function setHeaderStatus(state, label) {
  statusDot.className   = "status-dot " + state;
  statusText.textContent = label;
}
function setCallStatus(type, text) {
  callStatusCtr.innerHTML = text
    ? `<span class="status-pill ${type}">${text}</span>` : "";
}

// ── Audio ─────────────────────────────────────────────────────────────────
// iphone_tune.mp3 plays when user clicks Call, stops when Sarah starts speaking.
// hangup.wav plays when the call ends.
let ringAudio = null;

function startRingingSound() {
  stopRingingSound();
  ringAudio = new Audio("/static/iphone_tune.mp3");
  ringAudio.loop = true;
  ringAudio.volume = 1.0;
  ringAudio.play().then(() => {
    console.log("🔔 iPhone ringtone started");
  }).catch(err => {
    console.warn("🔔 Ring play failed:", err);
  });
}

function stopRingingSound() {
  if (ringAudio) {
    ringAudio.pause();
    ringAudio.currentTime = 0;
    ringAudio = null;
    console.log("🔕 Ringtone stopped");
  }
}

function playHangUpSound() {
  const audio = new Audio("/static/hangup.wav");
  audio.volume = 0.8;
  audio.play().then(() => {
    console.log("📵 Hang-up sound played");
  }).catch(err => {
    console.warn("📵 Hangup play failed:", err);
  });
}

// ── Fetch assistant config from backend ───────────────────────────────────
async function fetchAssistantConfig(maxRetries = 15) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const res = await fetch(`${API_BASE}/api/assistant-id`);
      if (res.ok) {
        const data = await res.json();
        if (data.assistant_id && data.public_key) return data;
      }
    } catch (e) {
      console.warn(`Backend not ready (attempt ${i+1}):`, e.message);
    }
    await sleep(2000);
  }
  return null;
}

// ── Bind VAPI events ──────────────────────────────────────────────────────
function bindVapiEvents() {
  vapiInstance.on("call-start", () => {
    // Don't stop ringtone here — it fires instantly before Sarah speaks.
    // Ringtone will be stopped by speech-start when Sarah actually talks.
    callActive = true;
    setCallStatus("active", "🟢 Connected — waiting for Sarah...");
    setHeaderStatus("active", "In Call");
    callBtn.classList.remove("ringing");
    callBtn.classList.add("in-call");
    callBtn.disabled    = false;
    callLabel.textContent = "End Call";
    phoneIcon.style.display = "none";
    endIcon.style.display   = "block";
    callHint.textContent  = "Click to end the call";
    callRingOuter.classList.remove("visible");
    callRingInner.classList.remove("visible");
    transcriptSection.style.display = "block";
    if (transcript.length === 0) transcriptBox.innerHTML = "";
  });

  vapiInstance.on("call-end", () => {
    callActive = false;
    stopRingingSound();
    playHangUpSound();
    setCallStatus("ended", "📵 Call ended. Thank you for calling Handa Aesthetics and Plastics!");
    setHeaderStatus("ready", "Assistant Ready");
    callBtn.classList.remove("in-call", "ringing");
    callBtn.disabled      = false;
    callLabel.textContent = "Call Again";
    phoneIcon.style.display = "block";
    endIcon.style.display   = "none";
    callHint.textContent  = "Click to speak with Sarah again";
    callRingOuter.classList.remove("visible");
    callRingInner.classList.remove("visible");
    visualWave.classList.remove("active");
  });

  vapiInstance.on("message", (msg) => {
    if (msg.type === "transcript" && msg.transcriptType === "final") {
      addTranscriptMsg(msg.role, msg.transcript);
    }
  });

  vapiInstance.on("speech-start", () => {
    stopRingingSound(); // Stop iPhone ringtone when Sarah starts speaking
    visualWave.classList.add("active");
  });
  vapiInstance.on("speech-end",   () => { if (!callActive) visualWave.classList.remove("active"); });

  vapiInstance.on("error", (err) => {
    stopRingingSound();
    console.error("VAPI error:", err);
    const msg = err?.error?.message || err?.message || JSON.stringify(err);
    setCallStatus("ended", `⚠️ ${msg}`);
    setHeaderStatus("error", "Error");
    callBtn.classList.remove("in-call", "ringing");
    callBtn.disabled      = false;
    callLabel.textContent = "Call Now";
    phoneIcon.style.display = "block";
    endIcon.style.display   = "none";
    callRingOuter.classList.remove("visible");
    callRingInner.classList.remove("visible");
    callActive = false;
  });
}

// ── Main init ─────────────────────────────────────────────────────────────
async function initVapi() {
  setHeaderStatus("", "Connecting...");
  callBtn.disabled = true;
  callBtn.classList.add("loading");
  callLabel.textContent = "Loading...";
  setCallStatus("connecting", "⏳ Starting up...");

  // Fetch assistant config from backend
  const config = await fetchAssistantConfig(15);
  if (!config) {
    setHeaderStatus("error", "Backend Unreachable");
    setCallStatus("ended", "❌ Could not reach backend on port 8000. Is the server running?");
    callBtn.classList.remove("loading");
    callLabel.textContent = "Unavailable";
    return;
  }

  assistantId = config.assistant_id;
  const publicKey = config.public_key;
  console.log("✅ Config loaded. Assistant:", assistantId);

  // Initialise VAPI with ESM-imported class
  try {
    vapiInstance = new Vapi(publicKey);
    bindVapiEvents();
  } catch (e) {
    console.error("Failed to init VAPI:", e);
    setHeaderStatus("error", "VAPI Init Failed");
    setCallStatus("ended", `❌ VAPI init error: ${e.message}`);
    callBtn.classList.remove("loading");
    callLabel.textContent = "Error";
    return;
  }

  callBtn.classList.remove("loading");
  callBtn.disabled      = false;
  callLabel.textContent = "Call Now";
  setHeaderStatus("ready", "Assistant Ready");
  setCallStatus("", "");
  console.log("✅ VAPI receptionist ready. Click Call Now!");
}

// ── Call button ───────────────────────────────────────────────────────────
callBtn.addEventListener("click", async () => {
  console.log(">>> CALL BUTTON CLICKED");
  console.log(">>> vapiInstance:", !!vapiInstance, "assistantId:", assistantId, "callActive:", callActive);

  if (!vapiInstance || !assistantId) {
    console.log(">>> EXITING: no vapiInstance or assistantId");
    return;
  }

  if (callActive) {
    console.log(">>> STOPPING active call");
    vapiInstance.stop();
    return;
  }

  console.log(">>> Setting up UI for ringing...");
  callBtn.disabled      = true;
  callBtn.classList.add("ringing");
  callLabel.textContent = "Ringing...";
  callRingOuter.classList.add("visible");
  callRingInner.classList.add("visible");
  setCallStatus("connecting", "📞 Connecting to Sarah...");
  setHeaderStatus("active", "Connecting...");

  console.log(">>> About to call startRingingSound()");
  startRingingSound();
  console.log(">>> startRingingSound() returned");

  try {
    console.log(">>> About to call vapiInstance.start()");
    await vapiInstance.start(assistantId);
    console.log(">>> vapiInstance.start() resolved");
    callBtn.disabled = false;
  } catch (err) {
    stopRingingSound();
    console.error(">>> Failed to start call:", err);
    callBtn.classList.remove("ringing");
    callBtn.disabled      = false;
    callLabel.textContent = "Call Now";
    callRingOuter.classList.remove("visible");
    callRingInner.classList.remove("visible");
    setCallStatus("ended", `❌ ${err?.message || "Failed to start call"}`);
    setHeaderStatus("ready", "Assistant Ready");
  }
});

// ── Transcript ────────────────────────────────────────────────────────────
function addTranscriptMsg(role, text) {
  if (!text?.trim()) return;
  transcript.push({ role, text });
  const isUser = role === "user";
  const el = document.createElement("div");
  el.className = `msg ${isUser ? "user" : "assistant"}`;
  el.innerHTML = `
    <div class="msg-avatar">${isUser ? "🧑" : "🤖"}</div>
    <div>
      <div class="msg-role">${isUser ? "You" : "Sarah"}</div>
      <div class="msg-bubble">${isUser ? escHtml(text) : renderMarkdown(text)}</div>
    </div>`;
  transcriptBox.appendChild(el);
  transcriptBox.scrollTop = transcriptBox.scrollHeight;
}

clearBtn.addEventListener("click", () => {
  transcript = [];
  transcriptBox.innerHTML = `<div class="transcript-empty">Conversation will appear here...</div>`;
});

// ── File upload ───────────────────────────────────────────────────────────
uploadZone.addEventListener("dragover",  e => { e.preventDefault(); uploadZone.classList.add("drag-over"); });
uploadZone.addEventListener("dragleave", ()  => uploadZone.classList.remove("drag-over"));
uploadZone.addEventListener("drop", e => {
  e.preventDefault(); uploadZone.classList.remove("drag-over");
  handleFiles(e.dataTransfer.files);
});
fileInput.addEventListener("change", () => handleFiles(fileInput.files));

async function handleFiles(files) {
  if (!files?.length) return;
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  uploadStatus.textContent = `⏳ Uploading ${files.length} file(s)...`;
  uploadStatus.className   = "upload-status loading";
  try {
    const res  = await fetch(`${API_BASE}/api/upload-docs`, { method: "POST", body: fd });
    const data = await res.json();
    uploadStatus.textContent = res.ok ? `✅ ${data.message}` : `❌ ${data.detail || "Upload failed"}`;
    uploadStatus.className   = res.ok ? "upload-status success" : "upload-status error";
  } catch (e) {
    uploadStatus.textContent = `❌ Network error: ${e.message}`;
    uploadStatus.className   = "upload-status error";
  }
  fileInput.value = "";
}

// ── RAG query tester ──────────────────────────────────────────────────────
queryBtn.addEventListener("click", doQuery);
queryInput.addEventListener("keydown", e => { if (e.key === "Enter") doQuery(); });

async function doQuery() {
  const q = queryInput.value.trim();
  if (!q) return;
  queryBtn.disabled     = true;
  queryBtn.textContent  = "...";
  queryResult.textContent = "Searching...";
  queryResult.className   = "query-result visible";
  try {
    const res  = await fetch(`${API_BASE}/api/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    });
    const data = await res.json();
    queryResult.textContent = data.context || "No results found.";
  } catch (e) {
    queryResult.textContent = `Error: ${e.message}`;
  }
  queryBtn.disabled    = false;
  queryBtn.textContent = "Ask";
}

// ── Boot ──────────────────────────────────────────────────────────────────────
initVapi();
initChat();

// ── Chat Widget ───────────────────────────────────────────────────────────────
function initChat() {
  const chatBtn      = document.getElementById("chatButton");
  const chatWidget   = document.getElementById("chatWidget");
  const chatClose    = document.getElementById("chatWidgetClose");
  const chatMessages = document.getElementById("chatMessages");
  const chatInput    = document.getElementById("chatInput");
  const chatSendBtn  = document.getElementById("chatSendBtn");
  const chatTyping   = document.getElementById("chatTyping");

  // Chat history for multi-turn context
  let chatHistory = [];
  let chatOpen    = false;
  let isSending   = false;

  // ── Open / Close ─────────────────────────────────────────────────
  function openChat() {
    chatOpen = true;
    chatWidget.classList.add("open");
    chatWidget.setAttribute("aria-hidden", "false");
    chatInput.focus();
    // Show greeting if first open
    if (chatHistory.length === 0) {
      addBubble("assistant", "👋 Hi! I'm Sarah from Handa Aesthetics and Plastics. How can I help you today?");
    }
  }

  function closeChat() {
    chatOpen = false;
    chatWidget.classList.remove("open");
    chatWidget.setAttribute("aria-hidden", "true");
  }

  chatBtn.addEventListener("click", () => {
    chatOpen ? closeChat() : openChat();
  });
  chatClose.addEventListener("click", closeChat);

  // Close on Escape
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && chatOpen) closeChat();
  });

  // ── Send message ─────────────────────────────────────────────────
  chatSendBtn.addEventListener("click", sendMessage);
  chatInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });

  async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text || isSending) return;

    isSending = true;
    chatInput.value = "";
    chatSendBtn.disabled = true;

    // Render user bubble
    addBubble("user", text);
    chatHistory.push({ role: "user", content: text });

    // Show typing indicator
    chatTyping.style.display = "flex";
    scrollMessages();

    try {
      const res  = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history: chatHistory.slice(0, -1) }),
      });
      const data = await res.json();
      const reply = data.reply || "Sorry, I couldn't process that. Please try again.";

      chatTyping.style.display = "none";
      addBubble("assistant", reply);
      chatHistory.push({ role: "assistant", content: reply });

      // Keep history bounded
      if (chatHistory.length > 20) chatHistory = chatHistory.slice(-20);

    } catch (err) {
      chatTyping.style.display = "none";
      addBubble("assistant", "⚠️ Network error. Please check the server and try again.");
      console.error("Chat error:", err);
    }

    isSending = false;
    chatSendBtn.disabled = false;
    chatInput.focus();
  }

  // Chat bubbles rendering will use the top-level renderMarkdown function

  // ── Render bubble ─────────────────────────────────────────────────
  function addBubble(role, text) {
    const isUser = role === "user";
    const row = document.createElement("div");
    row.className = `chat-bubble-row ${isUser ? "user" : "assistant"}`;

    const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const content = isUser ? escHtml(text) : renderMarkdown(text);
    row.innerHTML = `
      <div class="chat-bubble">${content}</div>
      <div class="chat-bubble-meta">${time}</div>`;

    chatMessages.appendChild(row);
    scrollMessages();
  }

  function scrollMessages() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
}
