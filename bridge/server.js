#!/usr/bin/env node

/**
 * Graphic Density — API Bridge
 * 
 * Native Messaging host that runs a local HTTP server.
 * Chrome extension communicates via stdin/stdout (native messaging protocol).
 * External clients (Python, curl, benchmark harness) hit HTTP endpoints.
 * 
 * Endpoints:
 *   GET  /state?mode=numbered|full|actions_only  → page state
 *   GET  /environment                             → full environment summary
 *   POST /action                                  → execute single action
 *   POST /batch                                   → execute action sequence
 *   GET  /history                                 → action history
 *   DELETE /history                               → clear history
 *   GET  /health                                  → connection status
 *   POST /navigate                                → navigate to URL
 *   GET  /tabs                                    → list open tabs
 */

const http = require('http');
const { URL } = require('url');

const PORT = 7080;
const HOST = '127.0.0.1';

// ── Native Messaging Protocol ────────────────────────────────────
// Chrome sends/receives messages as: [4-byte length][JSON payload]

let pendingRequests = new Map();
let requestId = 0;
let extensionConnected = false;

function sendToExtension(msg) {
  const json = JSON.stringify(msg);
  const buffer = Buffer.alloc(4 + Buffer.byteLength(json));
  buffer.writeUInt32LE(Buffer.byteLength(json), 0);
  buffer.write(json, 4);
  process.stdout.write(buffer);
}

function readNativeMessage(buffer) {
  const messages = [];
  let offset = 0;

  while (offset + 4 <= buffer.length) {
    const length = buffer.readUInt32LE(offset);
    if (offset + 4 + length > buffer.length) break;
    const json = buffer.slice(offset + 4, offset + 4 + length).toString();
    try {
      messages.push(JSON.parse(json));
    } catch (e) {
      logError('Failed to parse native message:', e.message);
    }
    offset += 4 + length;
  }

  return { messages, remaining: buffer.slice(offset) };
}

// Buffer for incoming native messages (they can arrive in chunks)
let inputBuffer = Buffer.alloc(0);

process.stdin.on('data', (chunk) => {
  inputBuffer = Buffer.concat([inputBuffer, chunk]);

  const { messages, remaining } = readNativeMessage(inputBuffer);
  inputBuffer = remaining;

  for (const msg of messages) {
    handleExtensionMessage(msg);
  }
});

process.stdin.on('end', () => {
  logInfo('Extension disconnected (stdin closed). Shutting down.');
  process.exit(0);
});

function handleExtensionMessage(msg) {
  // Connection handshake
  if (msg.type === 'CONNECTED') {
    extensionConnected = true;
    logInfo('Extension connected.');
    return;
  }

  // Response to a pending request
  if (msg.requestId !== undefined && pendingRequests.has(msg.requestId)) {
    const { resolve, timer } = pendingRequests.get(msg.requestId);
    clearTimeout(timer);
    pendingRequests.delete(msg.requestId);
    resolve(msg.response);
    return;
  }
}

function requestFromExtension(payload, timeout = 30000) {
  return new Promise((resolve, reject) => {
    const id = ++requestId;

    const timer = setTimeout(() => {
      pendingRequests.delete(id);
      reject(new Error('Extension response timeout'));
    }, timeout);

    pendingRequests.set(id, { resolve, reject, timer });

    sendToExtension({ requestId: id, ...payload });
  });
}

// ── HTTP Server ──────────────────────────────────────────────────

const server = http.createServer(async (req, res) => {
  // CORS headers for local development
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Content-Type', 'application/json');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  if (!extensionConnected) {
    respond(res, 503, { error: 'Extension not connected. Open Chrome with the Graphic Density extension.' });
    return;
  }

  try {
    const url = new URL(req.url, `http://${HOST}:${PORT}`);
    const path = url.pathname;

    // ── GET /state ───────────────────────────────────────────
    if (req.method === 'GET' && path === '/state') {
      const mode = url.searchParams.get('mode') || 'numbered';
      const tabId = url.searchParams.get('tab') ? parseInt(url.searchParams.get('tab')) : null;

      const result = await requestFromExtension({
        type: 'API_GET_STATE',
        mode,
        tabId,
      });

      respond(res, 200, result);
      return;
    }

    // ── GET /environment ─────────────────────────────────────
    if (req.method === 'GET' && path === '/environment') {
      const tabId = url.searchParams.get('tab') ? parseInt(url.searchParams.get('tab')) : null;

      const result = await requestFromExtension({
        type: 'API_GET_ENVIRONMENT',
        tabId,
      });

      respond(res, 200, result);
      return;
    }

    // ── POST /action ─────────────────────────────────────────
    if (req.method === 'POST' && path === '/action') {
      const body = await readBody(req);
      const action = JSON.parse(body);

      const result = await requestFromExtension({
        type: 'API_EXECUTE_ACTION',
        action,
      });

      respond(res, 200, result);
      return;
    }

    // ── POST /batch ──────────────────────────────────────────
    if (req.method === 'POST' && path === '/batch') {
      const body = await readBody(req);
      const { actions } = JSON.parse(body);

      const result = await requestFromExtension({
        type: 'API_EXECUTE_BATCH',
        actions,
      });

      respond(res, 200, result);
      return;
    }

    // ── GET /history ─────────────────────────────────────────
    if (req.method === 'GET' && path === '/history') {
      const result = await requestFromExtension({ type: 'API_GET_HISTORY' });
      respond(res, 200, result);
      return;
    }

    // ── DELETE /history ──────────────────────────────────────
    if (req.method === 'DELETE' && path === '/history') {
      const result = await requestFromExtension({ type: 'API_CLEAR_HISTORY' });
      respond(res, 200, result);
      return;
    }

    // ── POST /navigate ───────────────────────────────────────
    if (req.method === 'POST' && path === '/navigate') {
      const body = await readBody(req);
      const { url: targetUrl, tabId } = JSON.parse(body);

      const result = await requestFromExtension({
        type: 'API_NAVIGATE',
        url: targetUrl,
        tabId,
      });

      respond(res, 200, result);
      return;
    }

    // ── GET /tabs ────────────────────────────────────────────
    if (req.method === 'GET' && path === '/tabs') {
      const result = await requestFromExtension({ type: 'API_GET_TABS' });
      respond(res, 200, result);
      return;
    }

    // ── GET /health ──────────────────────────────────────────
    if (req.method === 'GET' && path === '/health') {
      respond(res, 200, {
        status: 'ok',
        extensionConnected,
        pendingRequests: pendingRequests.size,
        uptime: process.uptime(),
      });
      return;
    }

    // ── 404 ──────────────────────────────────────────────────
    respond(res, 404, {
      error: 'Not found',
      endpoints: [
        'GET  /state?mode=numbered|full|actions_only',
        'GET  /environment',
        'POST /action',
        'POST /batch',
        'GET  /history',
        'DELETE /history',
        'POST /navigate',
        'GET  /tabs',
        'GET  /health',
      ],
    });

  } catch (err) {
    logError('Request error:', err.message);
    respond(res, 500, { error: err.message });
  }
});

server.listen(PORT, HOST, () => {
  logInfo(`API server listening on http://${HOST}:${PORT}`);
});

// ── Utilities ────────────────────────────────────────────────────

function respond(res, status, data) {
  res.writeHead(status);
  res.end(JSON.stringify(data, null, 2));
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (chunk) => chunks.push(chunk));
    req.on('end', () => resolve(Buffer.concat(chunks).toString()));
    req.on('error', reject);
  });
}

// Log to stderr (stdout is reserved for native messaging)
function logInfo(...args) {
  process.stderr.write(`[GD Bridge] ${args.join(' ')}\n`);
}

function logError(...args) {
  process.stderr.write(`[GD Bridge ERROR] ${args.join(' ')}\n`);
}

// Notify extension we're ready
sendToExtension({ type: 'BRIDGE_READY' });
logInfo('Bridge started. Waiting for extension connection...');
