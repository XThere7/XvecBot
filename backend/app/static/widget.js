/* XvecBot embeddable chat widget (Phase 4) — vanilla JS, no dependencies.
 * <script src="https://yourplatform.com/widget.js" data-agent="TOKEN" async></script>
 * Optional: data-position="right|left"  data-color="#hex"  data-lang="English"
 * Exposes window.XvecBotWidget = { open, close, destroy } */
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

// One bubble per page.
if (window.XvecBotWidget && window.XvecBotWidget.destroy) {
  try { window.XvecBotWidget.destroy(); } catch (e) {}
}

var CSS = '' +
':host{all:initial}' +
'.r{position:fixed;inset:0;pointer-events:none;z-index:2147483000;color:#1f2937;font:14px/1.4 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}' +
'.r>*{pointer-events:auto}' +
'.p{position:absolute;bottom:88px;width:380px;height:520px;max-height:calc(100vh - 116px);background:#fff;border-radius:16px;box-shadow:0 12px 40px #1018282e;display:flex;flex-direction:column;overflow:hidden;animation:i .18s ease-out}' +
'.p[hidden]{display:none}' +
'@keyframes i{from{opacity:0;transform:translateY(10px) scale(.985)}to{opacity:1;transform:none}}' +
'.h{flex:0 0 auto;background:var(--c);color:#fff;padding:14px 16px;display:flex;gap:10px;align-items:flex-start;justify-content:space-between}' +
'.n{font-size:15px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
'.g{display:block;font-size:11px;font-weight:400;opacity:.85;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
'.g[hidden]{display:none}' +
'.x{flex:0 0 auto;width:28px;height:28px;border:0;border-radius:8px;font-size:19px;line-height:1;cursor:pointer;color:#fff;background:#ffffff2e}' +
'.x:hover{background:#ffffff4d}' +
'.l{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px;background:#f8fafc}' +
'.m{max-width:82%;padding:9px 12px;border-radius:12px;font-size:14px;white-space:pre-wrap;overflow-wrap:anywhere}' +
'.u{align-self:flex-end;background:var(--c);color:#fff;border-bottom-right-radius:4px}' +
'.b{align-self:flex-start;background:#fff;border:1px solid #e5e7eb;border-bottom-left-radius:4px}' +
'.e{align-self:flex-start;background:#fef2f2;border:1px solid #fecaca;color:#b91c1c}' +
'.s{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}' +
'.k{font-size:11px;line-height:1.6;color:#475569;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:999px;padding:1px 9px;text-decoration:none;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
'a.k:hover{background:#e2e8f0}' +
'.t{align-self:flex-start;display:flex;gap:4px;background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:13px 14px}' +
'.t i{width:6px;height:6px;border-radius:50%;background:#94a3b8;animation:d 1.2s infinite}' +
'.t i:nth-child(2){animation-delay:.16s}.t i:nth-child(3){animation-delay:.32s}' +
'@keyframes d{0%,60%,100%{opacity:.3;transform:none}30%{opacity:1;transform:translateY(-3px)}}' +
'.f{flex:0 0 auto;display:flex;gap:8px;padding:10px;border-top:1px solid #e5e7eb}' +
'.i{flex:1;min-width:0;border:1px solid #d1d5db;border-radius:10px;padding:10px 12px;font:inherit;color:#1f2937;background:#fff;outline:none}' +
'.i:focus{border-color:var(--c);box-shadow:0 0 0 3px #6366f11f}' +
'.o{flex:0 0 auto;width:40px;height:40px;border:0;border-radius:10px;background:var(--c);color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center}' +
'.o:disabled{opacity:.45;cursor:not-allowed}' +
'.a{flex:0 0 auto;display:block;text-align:center;font-size:11px;color:#94a3b8;padding:7px;border-top:1px solid #eef2f7;text-decoration:none}' +
'.z{position:absolute;bottom:24px;width:52px;height:52px;border:0;border-radius:50%;background:var(--c);color:#fff;cursor:pointer;padding:0;display:flex;align-items:center;justify-content:center;box-shadow:0 6px 20px #10182842;transition:transform .18s}' +
'.z:hover{transform:scale(1.07)}' +
'.z svg{width:24px;height:24px}' +
'.z .q{display:none}' +
'.z[aria-expanded="true"] .c1{display:none}' +
'.z[aria-expanded="true"] .q{display:block}' +
'@media (max-width:480px){.p{width:calc(100vw - 32px);height:min(520px,calc(100vh - 116px));bottom:84px}}';

// Shadow DOM keeps these styles off the host page.
var host = document.createElement('div');
host.id = 'xvecbot-' + Math.random().toString(36).slice(2, 9);
host.style.cssText = 'position:fixed;top:0;left:0;width:0;height:0';

var A = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';
var root = host.attachShadow({ mode: 'open' });
root.innerHTML = '<style>' + CSS + '</style><div class="r" style="--c:' + COLOR + '">' +
'<section class="p" hidden>' +
'<header class="h"><div style="min-width:0"><div class="n">AI Assistant</div><span class="g" hidden></span></div>' +
'<button class="x" type="button" aria-label="Close chat">&#215;</button></header>' +
'<div class="l" role="log" aria-live="polite"></div>' +
'<form class="f"><input class="i" type="text" maxlength="4000" placeholder="Type your message…" aria-label="Message" autocomplete="off">' +
'<button class="o" type="submit" aria-label="Send"><svg ' + A + ' width="18" height="18">' +
'<path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg></button></form>' +
'<a class="a" href="' + API_BASE + '" target="_blank" rel="noopener nofollow">Powered by XvecBot</a>' +
'</section>' +
'<button class="z" type="button" aria-label="Open chat" aria-expanded="false">' +
'<svg class="c1" ' + A + '><path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.9 8.9 0 0 1-4-.9L3 21l1.9-4.6A8.4 8.4 0 0 1 12 3.1a8.4 8.4 0 0 1 9 8.4z"/></svg>' +
'<svg class="q" ' + A + '><path d="M18 6 6 18M6 6l12 12"/></svg>' +
'</button></div>';

var $ = function (q) { return root.querySelector(q); };
var panel = $('.p'), log = $('.l'), form = $('.f'), input = $('.i'), send = $('.o'),
    bubble = $('.z'), nameEl = $('.n'), langEl = $('.g'), closeBtn = $('.x');
bubble.style[POS] = panel.style[POS] = '24px';
(document.body || document.documentElement).appendChild(host);

// Session state — closure only, no localStorage or cookies.
var messages = [], conversationId = null, info = null,
    inFlight = false, isOpen = false, greeted = false, dead = false, abort = null;

var ERR = {
  rate: "You're sending messages too quickly — please wait a moment.",
  denied: 'This chat is temporarily unavailable.',
  oops: 'Something went wrong. Please try again.'
};

function toBottom() { log.scrollTop = log.scrollHeight; }
function focusInput() { try { input.focus({ preventScroll: true }); } catch (e) { input.focus(); } }

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

function greet() {
  if (greeted) return;
  greeted = true;
  var who = info && info.name;
  addMessage('bot', who
    ? 'Hi, I’m ' + who + '. ' + (info.description ? info.description + ' ' : '') + 'How can I help you today?'
    : 'Hi! How can I help you today?');
}

function open() {
  if (dead || isOpen) return;
  isOpen = true;
  greet();
  panel.hidden = false;
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
  bubble.removeEventListener('click', toggle);
  closeBtn.removeEventListener('click', close);
  if (host.parentNode) host.parentNode.removeChild(host);
}

function onSubmit(e) {
  e.preventDefault();
  if (inFlight || dead) return;
  var text = (input.value || '').trim();
  if (!text) return;

  input.value = '';
  messages.push({ role: 'user', content: text });
  addMessage('user', text);            // optimistic — never wait on the API
  inFlight = true;
  send.disabled = input.disabled = true;
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
        messages.push({ role: 'assistant', content: answer });
        addMessage('bot', answer, r.d.sources);
      } else {
        addError(ERR.oops);            // empty or malformed answer
      }
    })
    .catch(function () { dropTyping(typing); if (!dead) addError(ERR.oops); })
    .then(function () {
      abort = null;
      if (dead) return;
      inFlight = false;
      send.disabled = input.disabled = false;
      focusInput();
    });
}

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
bubble.addEventListener('click', toggle);
closeBtn.addEventListener('click', close);
document.addEventListener('keydown', onKey);

window.XvecBotWidget = { open: open, close: close, destroy: destroy };
})();
