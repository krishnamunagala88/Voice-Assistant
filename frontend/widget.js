/**
 * widget.js — Portable AI Voice & Chat Assistant Widget
 * Designed to be embedded into any client's website with a simple HTML snippet.
 */

(function () {
  // 1. Prevent duplicate loading
  if (window.__ClinicAIWidgetLoaded) return;
  window.__ClinicAIWidgetLoaded = true;

  // 2. Locate container and read configuration attributes
  const container = document.getElementById("clinic-ai-widget");
  if (!container) {
    console.error("Clinic AI Widget error: Elements with ID 'clinic-ai-widget' not found on the page.");
    return;
  }

  // Get configuration from data attributes (fallback to script's origin or current domain)
  const scriptTag = document.currentScript;
  const scriptBaseUrl = scriptTag ? new URL(scriptTag.src).origin : window.location.origin;
  
  const backendUrl = container.getAttribute("data-backend-url") || scriptBaseUrl;
  const assistantName = container.getAttribute("data-assistant-name") || "Sarah";
  const assistantRole = container.getAttribute("data-assistant-role") || "AI Receptionist";

  // State Management
  let vapiInstance = null;
  let assistantId = null;
  let publicKey = null;
  let callActive = false;
  let chatHistory = [];
  let isSending = false;
  let chatOpen = false;
  let ringAudio = null;

  // 3. Inject CSS Styles directly to head to make snippet self-contained
  const styleEl = document.createElement("style");
  styleEl.textContent = `
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@600;700&display=swap');

    .vapi-w-wrapper {
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 999999;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }

    /* Floating Buttons Row */
    .vapi-w-buttons-row {
      display: flex;
      gap: 12px;
      align-items: center;
      justify-content: flex-end;
    }

    /* Floating Button Base */
    .vapi-w-btn {
      width: 60px;
      height: 60px;
      border-radius: 50%;
      border: none;
      cursor: pointer;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      color: white;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
      transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275), box-shadow 0.3s, background 0.3s;
      position: relative;
    }
    .vapi-w-btn:hover {
      transform: scale(1.08);
      box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
    }
    .vapi-w-btn:active {
      transform: scale(0.95);
    }

    /* Call Button Specifics */
    .vapi-w-btn-call {
      background: linear-gradient(135deg, #3b82f6, #06b6d4);
    }
    .vapi-w-btn-call:hover {
      box-shadow: 0 0 0 8px rgba(59, 130, 246, 0.2), 0 12px 32px rgba(0, 0, 0, 0.45);
    }
    .vapi-w-btn-call.ringing {
      animation: vapi-w-pulse-ring 1.5s infinite;
    }
    .vapi-w-btn-call.in-call {
      background: linear-gradient(135deg, #ef4444, #dc2626);
    }
    .vapi-w-btn-call.in-call:hover {
      box-shadow: 0 0 0 8px rgba(239, 68, 68, 0.2), 0 12px 32px rgba(0, 0, 0, 0.45);
    }
    .vapi-w-btn-call.loading {
      background: #475569;
      cursor: not-allowed;
    }

    /* Chat Button Specifics */
    .vapi-w-btn-chat {
      background: linear-gradient(135deg, #6366f1, #8b5cf6);
    }
    .vapi-w-btn-chat:hover {
      box-shadow: 0 0 0 8px rgba(99, 102, 241, 0.2), 0 12px 32px rgba(0, 0, 0, 0.45);
    }
    .vapi-w-btn-chat.open-active {
      background: #1e1b4b;
      transform: rotate(90deg);
    }

    /* Ring pulse animation */
    @keyframes vapi-w-pulse-ring {
      0% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.6), 0 8px 24px rgba(0,0,0,0.35); }
      70% { box-shadow: 0 0 0 16px rgba(59, 130, 246, 0), 0 8px 24px rgba(0,0,0,0.35); }
      100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0), 0 8px 24px rgba(0,0,0,0.35); }
    }

    /* SVGs size */
    .vapi-w-btn svg {
      width: 24px;
      height: 24px;
      display: block;
    }

    /* Tooltip labels */
    .vapi-w-tooltip {
      position: absolute;
      bottom: 72px;
      background: rgba(15, 23, 42, 0.95);
      color: #f8fafc;
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 11px;
      font-weight: 500;
      white-space: nowrap;
      pointer-events: none;
      opacity: 0;
      transform: translateY(6px);
      transition: opacity 0.2s, transform 0.2s;
      border: 1px solid rgba(255, 255, 255, 0.1);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    }
    .vapi-w-btn:hover .vapi-w-tooltip {
      opacity: 1;
      transform: translateY(0);
    }

    /* Chat Widget Window */
    .vapi-w-chat-window {
      position: absolute;
      bottom: 80px;
      right: 0;
      width: 370px;
      height: 520px;
      max-height: calc(100vh - 140px);
      max-width: calc(100vw - 48px);
      background: rgba(9, 15, 30, 0.98);
      border: 1px solid rgba(99, 102, 241, 0.35);
      border-radius: 20px;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(99, 102, 241, 0.15);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      opacity: 0;
      transform: translateY(20px) scale(0.97);
      pointer-events: none;
      transition: opacity 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
    }
    .vapi-w-chat-window.open {
      opacity: 1;
      transform: translateY(0) scale(1);
      pointer-events: all;
    }

    /* Chat Header */
    .vapi-w-chat-header {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 16px 20px;
      background: linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(139, 92, 246, 0.1));
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      flex-shrink: 0;
    }
    .vapi-w-chat-avatar {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: linear-gradient(135deg, #6366f1, #8b5cf6);
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }
    .vapi-w-chat-avatar svg {
      width: 18px;
      height: 18px;
      color: white;
    }
    .vapi-w-chat-title-info {
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .vapi-w-chat-name {
      font-size: 14px;
      font-weight: 700;
      color: #f8fafc;
    }
    .vapi-w-chat-status {
      font-size: 10px;
      color: #a3e635;
      display: flex;
      align-items: center;
      gap: 4px;
      font-weight: 500;
    }
    .vapi-w-chat-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #a3e635;
      box-shadow: 0 0 4px #a3e635;
      animation: vapi-w-blink-dot 2s infinite;
    }
    @keyframes vapi-w-blink-dot { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

    .vapi-w-chat-close {
      background: none;
      border: none;
      cursor: pointer;
      color: #94a3b8;
      padding: 4px;
      border-radius: 50%;
      display: flex;
      transition: background 0.2s, color 0.2s;
    }
    .vapi-w-chat-close:hover {
      background: rgba(255, 255, 255, 0.08);
      color: #f8fafc;
    }
    .vapi-w-chat-close svg {
      width: 20px;
      height: 20px;
    }

    /* Messages Area */
    .vapi-w-chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px 20px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      scroll-behavior: smooth;
    }

    .vapi-w-bubble-row {
      display: flex;
      gap: 8px;
      animation: vapi-w-fade-in 0.25s ease forwards;
    }
    .vapi-w-bubble-row.user {
      flex-direction: row-reverse;
    }
    .vapi-w-bubble {
      max-width: 78%;
      padding: 10px 14px;
      border-radius: 16px 16px 16px 4px;
      font-size: 13.5px;
      line-height: 1.5;
      word-break: break-word;
      border: 1px solid rgba(255, 255, 255, 0.06);
    }
    .vapi-w-bubble-row.user .vapi-w-bubble {
      background: linear-gradient(135deg, rgba(99, 102, 241, 0.25), rgba(139, 92, 246, 0.2));
      border-color: rgba(99, 102, 241, 0.3);
      border-radius: 16px 16px 4px 16px;
      color: #f8fafc;
    }
    .vapi-w-bubble-row.assistant .vapi-w-bubble {
      background: rgba(255, 255, 255, 0.04);
      color: #e2e8f0;
    }
    
    /* Markdown rendering styles */
    .vapi-w-bubble strong { font-weight: 700; color: #fff; }
    .vapi-w-bubble em { font-style: italic; }
    .vapi-w-bubble ul { margin: 6px 0; padding-left: 18px; list-style-type: disc; }
    .vapi-w-bubble ul li { margin-bottom: 4px; font-size: 13.5px; }
    
    .vapi-w-bubble-meta {
      font-size: 9px;
      color: #64748b;
      align-self: flex-end;
      margin-bottom: 2px;
      white-space: nowrap;
    }
    .vapi-w-bubble-row.user .vapi-w-bubble-meta {
      margin-right: 4px;
    }
    .vapi-w-bubble-row.assistant .vapi-w-bubble-meta {
      margin-left: 4px;
    }

    @keyframes vapi-w-fade-in {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }

    /* Typing Indicator */
    .vapi-w-typing {
      display: flex;
      gap: 4px;
      align-items: center;
      padding: 8px 20px;
    }
    .vapi-w-typing-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #64748b;
      animation: vapi-w-bounce 1.2s infinite;
    }
    .vapi-w-typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .vapi-w-typing-dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes vapi-w-bounce {
      0%, 80%, 100% { transform: translateY(0); opacity: 0.5; }
      40% { transform: translateY(-4px); opacity: 1; }
    }

    /* Chat Input Area */
    .vapi-w-input-row {
      display: flex;
      gap: 8px;
      padding: 16px 20px;
      background: rgba(0, 0, 0, 0.25);
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      align-items: center;
      flex-shrink: 0;
    }
    .vapi-w-input {
      flex: 1;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 12px;
      padding: 10px 14px;
      color: #f8fafc;
      font-size: 13.5px;
      outline: none;
      transition: border-color 0.2s, background 0.2s;
    }
    .vapi-w-input:focus {
      border-color: rgba(99, 102, 241, 0.6);
      background: rgba(255, 255, 255, 0.07);
    }
    .vapi-w-input::placeholder {
      color: #64748b;
    }
    
    .vapi-w-send {
      width: 38px;
      height: 38px;
      border-radius: 10px;
      border: none;
      background: linear-gradient(135deg, #6366f1, #8b5cf6);
      color: white;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: opacity 0.2s, transform 0.1s;
      flex-shrink: 0;
    }
    .vapi-w-send:hover { opacity: 0.9; }
    .vapi-w-send:active { transform: scale(0.92); }
    .vapi-w-send:disabled { opacity: 0.4; cursor: not-allowed; }
    .vapi-w-send svg {
      width: 16px;
      height: 16px;
    }

    /* Scrollbars */
    .vapi-w-chat-messages::-webkit-scrollbar { width: 5px; }
    .vapi-w-chat-messages::-webkit-scrollbar-track { background: transparent; }
    .vapi-w-chat-messages::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }
    
    /* Call Status overlay banner inside chat or standalone */
    .vapi-w-call-status-banner {
      background: rgba(16, 185, 129, 0.15);
      border-bottom: 1px solid rgba(16, 185, 129, 0.2);
      color: #34d399;
      font-size: 11px;
      text-align: center;
      padding: 6px 12px;
      animation: vapi-w-fade-in 0.3s ease;
      font-weight: 500;
    }
    .vapi-w-call-status-banner.error {
      background: rgba(239, 68, 68, 0.15);
      border-bottom: 1px solid rgba(239, 68, 68, 0.2);
      color: #f87171;
    }
    .vapi-w-call-status-banner.connecting {
      background: rgba(245, 158, 11, 0.15);
      border-bottom: 1px solid rgba(245, 158, 11, 0.2);
      color: #fbbf24;
    }
  `;
  document.head.appendChild(styleEl);

  // 4. Create DOM elements
  container.innerHTML = `
    <div class="vapi-w-wrapper">
      
      <!-- Chat Widget Popup Window -->
      <div class="vapi-w-chat-window" id="vapiChatWindow">
        <!-- Optional Call Banner (only active when call runs) -->
        <div id="vapiCallBanner" style="display:none;"></div>

        <!-- Chat Header -->
        <div class="vapi-w-chat-header">
          <div class="vapi-w-chat-avatar">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z" fill="currentColor" />
            </svg>
          </div>
          <div class="vapi-w-chat-title-info">
            <span class="vapi-w-chat-name">${escHtml(assistantName)}</span>
            <span class="vapi-w-chat-status">
              <span class="vapi-w-chat-dot"></span> Online
            </span>
          </div>
          <button class="vapi-w-chat-close" id="vapiChatClose" aria-label="Close Chat">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
            </svg>
          </button>
        </div>

        <!-- Chat Messages -->
        <div class="vapi-w-chat-messages" id="vapiChatMessages">
          <!-- Injected dynamically -->
        </div>

        <!-- Chat Typing Indicator -->
        <div class="vapi-w-typing" id="vapiChatTyping" style="display: none;">
          <span class="vapi-w-typing-dot"></span>
          <span class="vapi-w-typing-dot"></span>
          <span class="vapi-w-typing-dot"></span>
        </div>

        <!-- Chat Input Row -->
        <div class="vapi-w-input-row">
          <input type="text" class="vapi-w-input" id="vapiChatInput" placeholder="Type a message..." autocomplete="off" maxlength="500" />
          <button class="vapi-w-send" id="vapiChatSendBtn" aria-label="Send message">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Floating Buttons Row -->
      <div class="vapi-w-buttons-row">
        
        <!-- Floating Call Button -->
        <button class="vapi-w-btn vapi-w-btn-call" id="vapiCallBtn" aria-label="Start Call">
          <span class="vapi-w-tooltip" id="vapiCallTooltip">Call Agent</span>
          <!-- Phone Icon -->
          <svg id="vapiPhoneIcon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z" fill="currentColor"/>
          </svg>
          <!-- Hangup Icon -->
          <svg id="vapiHangupIcon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="display: none;">
            <path d="M12 9c-1.6 0-3.15.25-4.6.72v3.1c0 .39-.23.74-.56.9-.98.49-1.87 1.12-2.66 1.85-.18.18-.43.28-.7.28-.28 0-.53-.11-.71-.29L.29 13.08c-.18-.17-.29-.42-.29-.7 0-.28.11-.53.29-.71C3.34 8.78 7.46 7 12 7s8.66 1.78 11.71 4.67c.18.18.29.43.29.71 0 .28-.11.53-.29.71l-2.48 2.48c-.18.18-.43.29-.71.29-.27 0-.52-.1-.7-.28-.79-.74-1.69-1.36-2.67-1.85-.33-.16-.56-.5-.56-.9v-3.1C15.15 9.25 13.6 9 12 9z" fill="currentColor"/>
          </svg>
        </button>

        <!-- Floating Chat Button -->
        <button class="vapi-w-btn vapi-w-btn-chat" id="vapiChatBtn" aria-label="Open Chat">
          <span class="vapi-w-tooltip" id="vapiChatTooltip">Chat with AI</span>
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z" fill="currentColor" />
          </svg>
        </button>

      </div>
    </div>
  `;

  // Get references to elements
  const chatBtn      = document.getElementById("vapiChatBtn");
  const chatTooltip  = document.getElementById("vapiChatTooltip");
  const chatWindow   = document.getElementById("vapiChatWindow");
  const chatClose    = document.getElementById("vapiChatClose");
  const chatMessages = document.getElementById("vapiChatMessages");
  const chatInput    = document.getElementById("vapiChatInput");
  const chatSendBtn  = document.getElementById("vapiChatSendBtn");
  const chatTyping   = document.getElementById("vapiChatTyping");

  const callBtn      = document.getElementById("vapiCallBtn");
  const callTooltip  = document.getElementById("vapiCallTooltip");
  const phoneIcon    = document.getElementById("vapiPhoneIcon");
  const hangupIcon   = document.getElementById("vapiHangupIcon");
  const callBanner   = document.getElementById("vapiCallBanner");

  // Helpers
  const sleep   = ms => new Promise(r => setTimeout(r, ms));
  function escHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Simple Markdown Renderer
  function renderMarkdown(text) {
    if (!text) return "";
    let html = escHtml(text);
    
    // Bold: **text**
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Italic: *text*
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    
    // Unordered lists
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
    if (inList) processedLines.push('</ul>');
    
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

  // 5. Sound effects (using full backend URL paths)
  function startRingingSound() {
    stopRingingSound();
    ringAudio = new Audio(`${backendUrl}/static/iphone_tune.mp3`);
    ringAudio.loop = true;
    ringAudio.volume = 1.0;
    ringAudio.play().catch(err => console.warn("Ring sound failed to play:", err));
  }

  function stopRingingSound() {
    if (ringAudio) {
      ringAudio.pause();
      ringAudio.currentTime = 0;
      ringAudio = null;
    }
  }

  function playHangUpSound() {
    const audio = new Audio(`${backendUrl}/static/hangup.wav`);
    audio.volume = 0.8;
    audio.play().catch(err => console.warn("Hangup sound failed to play:", err));
  }

  // 6. Dynamic VAPI SDK loader and initializer
  async function lazyInitVapi() {
    if (vapiInstance) return true;

    // Set loading UI on call button
    callBtn.classList.add("loading");
    callTooltip.textContent = "Connecting...";

    try {
      // Fetch assistant config from backend
      const res = await fetch(`${backendUrl}/api/assistant-id`);
      if (!res.ok) throw new Error("Could not fetch assistant config from " + backendUrl);
      const config = await res.json();
      
      assistantId = config.assistant_id;
      publicKey = config.public_key;

      if (!assistantId || !publicKey) throw new Error("Invalid config received from backend");

      // Dynamically load the SDK from NPM CDN using ESM import
      const VapiSDK = await import("https://cdn.jsdelivr.net/npm/@vapi-ai/web@latest/+esm");
      let Vapi = VapiSDK.default;
      if (Vapi && Vapi.default) {
        Vapi = Vapi.default;
      }
      if (!Vapi || typeof Vapi !== "function") {
        Vapi = VapiSDK.Vapi || VapiSDK;
      }

      vapiInstance = new Vapi(publicKey);
      bindVapiEvents();

      callBtn.classList.remove("loading");
      callTooltip.textContent = "Call Agent";
      return true;
    } catch (err) {
      console.error("Vapi Widget initialization failed:", err);
      callBtn.classList.remove("loading");
      callTooltip.textContent = "Call Failed";
      showCallStatusBanner("error", `⚠️ Connection failed: ${err.message}`);
      return false;
    }
  }

  function showCallStatusBanner(type, text) {
    if (!text) {
      callBanner.style.display = "none";
      callBanner.className = "vapi-w-call-status-banner";
      callBanner.textContent = "";
      return;
    }
    callBanner.style.display = "block";
    callBanner.className = `vapi-w-call-status-banner ${type}`;
    callBanner.textContent = text;
  }

  // Vapi events binders
  function bindVapiEvents() {
    vapiInstance.on("call-start", () => {
      callActive = true;
      callBtn.classList.remove("ringing");
      callBtn.classList.add("in-call");
      phoneIcon.style.display = "none";
      hangupIcon.style.display = "block";
      callTooltip.textContent = "Hang up";
      showCallStatusBanner("active", `🟢 Connected with ${assistantName}`);
    });

    vapiInstance.on("call-end", () => {
      callActive = false;
      stopRingingSound();
      playHangUpSound();
      callBtn.classList.remove("in-call", "ringing");
      phoneIcon.style.display = "block";
      hangupIcon.style.display = "none";
      callTooltip.textContent = "Call Agent";
      showCallStatusBanner("ended", "📵 Call ended. Thank you!");
      setTimeout(() => { if (!callActive) showCallStatusBanner(null); }, 4000);
    });

    vapiInstance.on("speech-start", () => {
      stopRingingSound();
    });

    vapiInstance.on("error", (err) => {
      stopRingingSound();
      console.error("Vapi call error:", err);
      const errMsg = err?.error?.message || err?.message || "Call error occurred";
      callActive = false;
      callBtn.classList.remove("in-call", "ringing");
      phoneIcon.style.display = "block";
      hangupIcon.style.display = "none";
      callTooltip.textContent = "Call Failed";
      showCallStatusBanner("error", `⚠️ ${errMsg}`);
    });
  }

  // Handle Call button click
  callBtn.addEventListener("click", async () => {
    if (callActive) {
      if (vapiInstance) vapiInstance.stop();
      return;
    }

    const ready = await lazyInitVapi();
    if (!ready) return;

    try {
      callBtn.classList.add("ringing");
      callTooltip.textContent = "Dialing...";
      showCallStatusBanner("connecting", `⏳ Dialing ${assistantName}...`);
      
      startRingingSound();
      await vapiInstance.start(assistantId);
    } catch (err) {
      stopRingingSound();
      console.error("Failed to start call:", err);
      callBtn.classList.remove("ringing");
      callTooltip.textContent = "Call Failed";
      showCallStatusBanner("error", `⚠️ Call failed: ${err.message}`);
    }
  });

  // ── Chat Functionality ──────────────────────────────────────────

  function openChat() {
    chatOpen = true;
    chatWindow.classList.add("open");
    chatBtn.classList.add("open-active");
    chatTooltip.textContent = "Close Chat";
    chatInput.focus();

    if (chatHistory.length === 0) {
      addBubble("assistant", `👋 Hi! I'm ${assistantName} from the Clinic. How can I help you today?`);
    }
  }

  function closeChat() {
    chatOpen = false;
    chatWindow.classList.remove("open");
    chatBtn.classList.remove("open-active");
    chatTooltip.textContent = "Chat with AI";
  }

  chatBtn.addEventListener("click", () => {
    chatOpen ? closeChat() : openChat();
  });
  
  chatClose.addEventListener("click", closeChat);

  // Close on Escape key press
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && chatOpen) closeChat();
  });

  // Message Sending
  chatSendBtn.addEventListener("click", sendChatMessage);
  chatInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChatMessage();
    }
  });

  async function sendChatMessage() {
    const text = chatInput.value.trim();
    if (!text || isSending) return;

    isSending = true;
    chatInput.value = "";
    chatSendBtn.disabled = true;

    // 1. Add User Bubble
    addBubble("user", text);
    chatHistory.push({ role: "user", content: text });

    // 2. Show typing indicator
    chatTyping.style.display = "flex";
    scrollMessages();

    try {
      // Call backend chat endpoint
      const res = await fetch(`${backendUrl}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history: chatHistory.slice(0, -1) })
      });

      if (!res.ok) throw new Error("Backend chat server returned error status");
      
      const data = await res.json();
      const reply = data.reply || "I'm sorry, I couldn't get a response. Please try again.";

      chatTyping.style.display = "none";
      addBubble("assistant", reply);
      chatHistory.push({ role: "assistant", content: reply });

      // Limit history length to 20 turns
      if (chatHistory.length > 20) {
        chatHistory = chatHistory.slice(-20);
      }
    } catch (err) {
      chatTyping.style.display = "none";
      addBubble("assistant", "⚠️ Connection error. Please verify the server is running.");
      console.error("Chat message failed:", err);
    }

    isSending = false;
    chatSendBtn.disabled = false;
    chatInput.focus();
  }

  function addBubble(role, text) {
    const isUser = role === "user";
    const row = document.createElement("div");
    row.className = `vapi-w-bubble-row ${isUser ? "user" : "assistant"}`;

    const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const content = isUser ? escHtml(text) : renderMarkdown(text);
    
    row.innerHTML = `
      <div class="vapi-w-bubble">${content}</div>
      <div class="vapi-w-bubble-meta">${time}</div>
    `;

    chatMessages.appendChild(row);
    scrollMessages();
  }

  function scrollMessages() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
})();
