/* XvecBot embeddable chat widget (Phase 4) — vanilla JS, no dependencies.
 * <script src="https://yourplatform.com/widget.js" data-agent="<EMBED_TOKEN>" async></script>
 * Optional: data-position="right|left" data-color="#hex" data-lang="English".
 * Global: window.XvecBotWidget = { open, close, destroy } */
(function () {
'use strict';

var tag = document.currentScript || document.querySelector('script[data-agent]');
if (!tag) { console.warn('[XvecBot] No script tag found'); return; }
var TOKEN = (tag.getAttribute('data-agent') || '').trim();
if (!TOKEN) { console.warn('[XvecBot] data-agent is required'); return; }

// The API lives on the same origin the widget was served from.
var API_BASE;
try { API_BASE = new URL(tag.getAttribute('src') || '', document.baseURI).origin; }
catch (e) { API_BASE = location.origin; }

var POS = (tag.getAttribute('data-position') || '').toLowerCase() === 'left' ? 'left' : 'right';
var LANG = (tag.getAttribute('data-lang') || '').trim();
var COLOR = (tag.getAttribute('data-color') || '').trim();
if (!/^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(COLOR)) COLOR = '#6366f1';

// One bubble per page. A second script tag replaces the first.
if (window.XvecBotWidget && window.XvecBotWidget.destroy) {
  try { window.XvecBotWidget.destroy(); } catch (e) {}
}

var CSS = '' +
':host{all:initial}' +
'.r{position:fixed;inset:0;pointer-events:none;z-index:2147483000;color:#1f2937;font:14px/1.4 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}' +
'.r>*{pointer-events:auto}' +
'.p{position:absolute;bottom:88px;right:24px;width:380px;height:520px;max-height:calc(100vh - 116px);' +
'background:#fff;border-radius:16px;box-shadow:0 12px 40px #1018282e;display:flex;flex-direction:column;' +
'overflow:hidden;animation:i .18s ease-out}' +
'.z{position:absolute;bottom:24px;right:24px;width:52px;height:52px;border:0;border-radius:50%;' +
'background:var(--c);color:#fff;cursor:pointer;padding:0;display:flex;align-items:center;' +
'justify-content:center;box-shadow:0 6px 20px #10182842}' +
'.r[data-pos=left] .p,.r[data-pos=left] .z{right:auto;left:24px}' +
'.p[hidden]{display:none}' +
'@keyframes i{from{opacity:0;transform:translateY(10px) scale(.985)}to{opacity:1;transform:none}}' +
'.h{flex:0 0 auto;background:var(--c);color:#fff;padding:14px 16px;display:flex;gap:10px;align-items:flex-start;justify-content:space-between}' +
'.n{font-size:15px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
'.g{display:block;font-size:11px;font-weight:400;opacity:.85;margin-top:2px;overflow:hidden;white-space:nowrap}' +
'.g[hidden]{display:none}' +
'.w{flex:0 0 auto;display:flex;gap:6px}' +
'.w button{width:28px;height:28px;border:0;border-radius:8px;cursor:pointer;color:#fff;background:#ffffff2e;' +
'display:flex;align-items:center;justify-content:center;padding:0}' +
'.w button:hover{background:#ffffff4d}' +
'.w svg{width:15px;height:15px}' +
'.l{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px;background:#f8fafc}' +
'.m{max-width:82%;padding:9px 12px;border-radius:12px;font-size:14px;white-space:pre-wrap;overflow-wrap:anywhere}' +
'.u{align-self:flex-end;background:var(--c);color:#fff;border-bottom-right-radius:4px}' +
'.b{align-self:flex-start;background:#fff;border:1px solid #e5e7eb;border-bottom-left-radius:4px}' +
'.e{align-self:flex-start;background:#fef2f2;border:1px solid #fecaca;color:#b91c1c}' +
'.s{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}' +
'.k{font-size:11px;line-height:1.6;color:#475569;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:999px;padding:1px 9px;text-decoration:none;max-width:100%;overflow:hidden}' +
'.t{align-self:flex-start;display:flex;gap:4px;background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:13px 14px}' +
'.t i{width:6px;height:6px;border-radius:50%;background:#94a3b8;animation:d 1.2s infinite}' +
'.t i:nth-child(2){animation-delay:.16s}.t i:nth-child(3){animation-delay:.32s}' +
'@keyframes d{0%,60%,100%{opacity:.3;transform:none}30%{opacity:1;transform:translateY(-3px)}}' +
'.f{flex:0 0 auto;display:flex;gap:8px;align-items:flex-end;padding:10px;border-top:1px solid #e5e7eb}' +
'.i{flex:1;min-width:0;max-height:92px;border:1px solid #d1d5db;border-radius:10px;padding:10px 12px;' +
'font:inherit;color:#1f2937;background:#fff;outline:none;resize:none;overflow-y:auto}' +
'.i:focus{border-color:var(--c);box-shadow:0 0 0 3px #6366f11f}' +
'.o{flex:0 0 auto;width:40px;height:40px;border:0;border-radius:10px;background:var(--c);color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center}' +
'.o:disabled{opacity:.45;cursor:not-allowed}' +
'.a{flex:0 0 auto;display:block;text-align:center;font-size:11px;color:#94a3b8;padding:7px;border-top:1px solid #eef2f7;text-decoration:none}' +
'.z svg{width:24px;height:24px}' +
'.z .q{display:none}' +
'.z[aria-expanded="true"] .c1{display:none}' +
'.z[aria-expanded="true"] .q{display:block}' +
'.bd{position:absolute;top:-4px;right:-4px;width:20px;height:20px;border-radius:999px;' +
'background:#ef4444;border:2px solid #fff;color:#fff;font-size:11px;font-weight:600;line-height:16px;text-align:center}' +
'.bd[hidden]{display:none}' +
'.r[data-pos=left] .bd{right:auto;left:-4px}' +
'@media (max-width:480px){' +
  '.p{width:calc(100vw - 32px);height:70vh;bottom:84px}' +
  '.p,.z{right:16px}' +
  '.r[data-pos=left] .p,.r[data-pos=left] .z{left:16px}' +
  '.r[data-pos=left] .bd{left:-4px}' +
'}';

// Shadow DOM keeps these styles off the host page.
var host = document.createElement('div');
host.id = 'xvecbot-' + Math.random().toString(36).slice(2, 9);
host.style.cssText = 'position:fixed;top:0;left:0;width:0;height:0';

var A = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';
var root = host.attachShadow({ mode: 'open' });
root.innerHTML = '<style>' + CSS + '</style><div class="r" data-pos="' + POS + '" style="--c:' + COLOR + '">' +
'<section class="p" hidden>' +
'<header class="h"><div style="min-width:0"><div class="n">AI Assistant</div><span class="g" hidden></span></div>' +
'<div class="w"><button class="w1" type="button" aria-label="New conversation" title="New conversation">' +
'<svg ' + A + '><path d="M20 11.5V20H4V4h8.5M18 2l4 4L12 16l-5 1 1-5Z"/></svg></button>' +
'<button class="x" type="button" aria-label="Close chat">&#215;</button></div></header>' +
'<div class="l" role="log" aria-live="polite"></div>' +
'<form class="f"><textarea class="i" rows="1" maxlength="4000" placeholder="Type your message…" ' +
'aria-label="Message"></textarea>' +
'<button class="o" type="submit" aria-label="Send"><svg ' + A + ' width="18" height="18">' +
'<path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg></button></form>' +
'<a class="a" href="' + API_BASE + '" target="_blank" rel="noopener nofollow">Powered by XvecBot</a>' +
'</section>' +
'<button class="z" type="button" aria-label="Open chat" aria-expanded="false">' +
'<svg class="c1" ' + A + '><path d="M12 3a9 9 0 0 0-9 9 9 9 0 0 0 1.2 4.4L3 21l4.7-1.1A9 9 0 1 0 12 3Z"/></svg>' +
'<svg class="q" ' + A + '><path d="M18 6 6 18M6 6l12 12"/></svg><span class="bd" hidden>1</span>' +
'</button></div>';

var $ = function (q) { return root.querySelector(q); };
var wrap = $('.r'), panel = $('.p'), log = $('.l'), form = $('.f'), input = $('.i'), send = $('.o'),
    bubble = $('.z'), badge = $('.bd'), nameEl = $('.n'), langEl = $('.g'),
    closeBtn = $('.x'), newBtn = $('.w1');
(document.body || document.documentElement).appendChild(host);

// ── Session state ──
var DEFAULT_WELCOME = 'Hi! How can I help you today?';
var STORE_KEY = 'xvecbot_conv_' + TOKEN;
var messages = [], conversationId = null, info = null,
    inFlight = false, isOpen = false, greeted = false, dead = false, abort = null;

var ERR = {
  rate: "You're sending messages too quickly — please wait a moment.",
  denied: 'This chat is temporarily unavailable.',
  oops: 'Something went wrong. Please try again.'
};

/* Part E — the conversation lives in sessionStorage, so navigating to another
   page on the same site resumes the thread for this tab only. */
function loadStore() {
  try {
    var raw = sessionStorage.getItem(STORE_KEY);
    var d = raw ? JSON.parse(raw) : null;
    return d && typeof d === 'object' ? d : null;
  } catch (e) { return null; }
}
function saveStore() {
  try {
    sessionStorage.setItem(STORE_KEY, JSON.stringify(
      { c: conversationId, m: messages, w: greeted }));
  } catch (e) { /* private mode / quota — the chat still works, just not across pages */ }
}
function dropStore() { try { sessionStorage.removeItem(STORE_KEY); } catch (e) {} }

function toBottom() { log.scrollTop = log.scrollHeight; }
function focusInput() { try { input.focus({ preventScroll: true }); } catch (e) { input.focus(); } }
function grow() {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 92) + 'px';
}
function setBusy(b) { inFlight = b; send.disabled = input.disabled = b; }

function addMessage(role, text, sources) {
  var el = document.createElement('div');
  el.className = 'm ' + (role === 'user' ? 'u' : 'b');
  el.textContent = text;   // textContent — an answer is never parsed as HTML
  if (sources && sources.length) {
    var box = document.createElement('div');
    box.className = 's';
    sources.forEach(function (src, i) {
      if (!src) return;
      var label = src.filename || src.title || src.url || 'Source ' + (i + 1);
      if (src.page != null) label += ' p.' + src.page;
      var chip = document.createElement(src.url ? 'a' : 'span');
      chip.className = 'k';
      chip.textContent = chip.title = label;
      if (src.url) { chip.href = src.url; chip.target = '_blank'; chip.rel = 'noopener nofollow'; }
      box.appendChild(chip);
    });
    if (box.childNodes.length) el.appendChild(box);
  }
  log.appendChild(el);
  toBottom();
  return el;
}

function addError(text) { addMessage('bot', text).className = 'm e'; toBottom(); }

function startTyping() {
  var el = document.createElement('div');
  el.className = 't';
  el.innerHTML = '<i></i><i></i><i></i>';
  log.appendChild(el);
  toBottom();
  return el;
}

function dropTyping(el) { if (el && el.parentNode) el.parentNode.removeChild(el); }

/* Part A — the owner's welcome_message, shown once as the first (visual-only)
   bubble. It is never pushed to `messages`, so it is not a conversation turn
   and is never sent to the API. */
function greet() {
  if (greeted) return;
  greeted = true;
  var w = (info && info.welcome_message || '').trim() || DEFAULT_WELCOME;
  addMessage('bot', w);
  saveStore();
}

// ── open / close / destroy ──
function open() {
  if (dead || isOpen) return;
  isOpen = true;
  greet();
  panel.hidden = false;
  badge.hidden = true;            // Part B — opening clears the unread marker
  bubble.setAttribute('aria-expanded', 'true');
  focusInput();
}
function close() {
  if (dead) return;
  isOpen = false;
  panel.hidden = true;
  bubble.setAttribute('aria-expanded', 'false');
}
function toggle() { isOpen ? close() : open(); }
function onKey(e) { if (e.key === 'Escape' && isOpen) close(); }

function destroy() {
  if (dead) return;
  dead = true;
  try { if (abort) abort.abort(); } catch (e) {}
  document.removeEventListener('keydown', onKey);
  form.removeEventListener('submit', onSubmit);
  input.removeEventListener('keydown', onInputKey);
  input.removeEventListener('input', grow);
  bubble.removeEventListener('click', toggle);
  closeBtn.removeEventListener('click', close);
  newBtn.removeEventListener('click', newChat);
  if (host.parentNode) host.parentNode.removeChild(host);
}

/* Part E — explicit reset. Drops the stored conversation and re-greets. */
function newChat() {
  dropStore();
  conversationId = null;
  messages = [];
  greeted = false;
  log.innerHTML = '';
  badge.hidden = true;
  greet();
  focusInput();
}

/* Part C — Enter sends, Shift+Enter inserts a newline. */
function onInputKey(e) {
  if (e.key !== 'Enter' || e.shiftKey) return;   // Shift+Enter falls through to the textarea
  e.preventDefault();
  onSubmit({ preventDefault: function () {} });
}

function onSubmit(e) {
  e.preventDefault();
  if (inFlight || dead) return;
  var text = (input.value || '').trim();
  if (!text) return;

  input.value = '';
  grow();
  messages.push({ role: 'user', content: text });
  addMessage('user', text);            // optimistic — never wait on the API
  setBusy(true);
  var typing = startTyping();

  abort = ('AbortController' in window) ? new AbortController() : null;
  var opts = {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: TOKEN, message: text, conversation_id: conversationId })
  };
  if (abort) opts.signal = abort.signal;

  fetch(API_BASE + '/public/chat', opts)
    .then(function (res) {
      return res.json().catch(function () { return {}; })
        .then(function (d) { return { s: res.status, d: d }; });
    })
    .then(function (r) {
      dropTyping(typing);
      if (r.s !== 200) {
        addError(r.s === 429 ? ERR.rate : (r.s === 403 || r.s === 401) ? ERR.denied : ERR.oops);
        return;
      }
      if (r.d && r.d.conversation_id) conversationId = r.d.conversation_id;
      var answer = r.d && r.d.answer;
      if (typeof answer === 'string' && answer.trim()) {
        messages.push({ role: 'assistant', content: answer, sources: r.d.sources });
        addMessage('bot', answer, r.d.sources);
        // Part B — a reply that lands while the window is closed is unread.
        if (!isOpen) badge.hidden = false;
      } else {
        addError(ERR.oops);            // empty or malformed answer
      }
      saveStore();
    })
    .catch(function () { dropTyping(typing); if (!dead) addError(ERR.oops); })
    .then(function () {
      abort = null;
      if (dead) return;
      setBusy(false);
      focusInput();
    });
}

// Restore a thread started earlier in this tab, then load the agent's display info.
(function restore() {
  var st = loadStore();
  if (!st) return;
  conversationId = st.c || null;
  greeted = !!st.w;
  (st.m || []).forEach(function (m) {
    if (m && m.content) { messages.push(m); addMessage(m.role, m.content, m.sources); }
  });
})();

fetch(API_BASE + '/public/agent/' + encodeURIComponent(TOKEN))
  .then(function (r) { return r.ok ? r.json() : null; })
  .then(function (d) {
    if (!d) return;                   // keep the generic label
    info = d;
    if (d.name) nameEl.textContent = d.name;
    var lang = LANG || d.language || '';
    if (lang) { langEl.textContent = lang; langEl.hidden = false; }
  })
  .catch(function () {});

form.addEventListener('submit', onSubmit);
input.addEventListener('keydown', onInputKey);
input.addEventListener('input', grow);
bubble.addEventListener('click', toggle);
closeBtn.addEventListener('click', close);
newBtn.addEventListener('click', newChat);
document.addEventListener('keydown', onKey);

window.XvecBotWidget = { open: open, close: close, destroy: destroy };
})();
