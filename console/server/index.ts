// Sales Mama Console server: localhost only. Serves the React app (Vite middleware),
// a WebSocket bridge to the Claude Code CLI, and read-only repo reads for chips and the rail.
import { createServer, type IncomingMessage } from 'node:http';
import { existsSync, readFileSync, watch } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { WebSocketServer, type WebSocket } from 'ws';
import { createServer as createVite } from 'vite';
import { Run } from './engine';
import { findRepoRoot, readRail, readSource } from './repo';
import type { ClientMsg, ServerMsg } from '../shared/protocol';

const HOST = '127.0.0.1';
const PORT = Number(process.env.MAMA_CONSOLE_PORT ?? 4173);
const consoleDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const root = findRepoRoot(consoleDir);
const allowedHosts = new Set([`localhost:${PORT}`, `127.0.0.1:${PORT}`]);

// Blocks DNS rebinding and other sites' pages from reaching the bridge.
function sameOrigin(req: IncomingMessage): boolean {
  if (!allowedHosts.has(String(req.headers.host))) return false;
  const origin = req.headers.origin;
  return !origin || allowedHosts.has(origin.replace(/^https?:\/\//, ''));
}

const vite = await createVite({
  root: consoleDir,
  configFile: join(consoleDir, 'vite.config.ts'),
  server: { middlewareMode: true, hmr: { port: PORT + 1, host: HOST } },
  appType: 'spa',
  logLevel: 'warn',
});

const http = createServer((req, res) => {
  if (!sameOrigin(req)) { res.writeHead(403).end('Forbidden'); return; }
  const url = new URL(req.url ?? '/', `http://${req.headers.host}`);
  if (url.pathname === '/api/source') {
    const file = readSource(root, url.searchParams.get('path') ?? '');
    if (!file) { res.writeHead(404, { 'content-type': 'text/plain' }).end('Not readable from the console.'); return; }
    res.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' }).end(JSON.stringify(file));
    return;
  }
  if (url.pathname === '/api/replay') {
    // Recorded streams for design review (?replay=mama-day). Never runs the CLI.
    const name = url.searchParams.get('name') ?? '';
    const file = join(consoleDir, 'test', 'fixtures', `${name}.jsonl`);
    if (!/^[a-z0-9-]+$/.test(name) || !existsSync(file)) { res.writeHead(404).end(); return; }
    res.writeHead(200, { 'content-type': 'text/plain; charset=utf-8' }).end(readFileSync(file, 'utf8'));
    return;
  }
  if (url.pathname === '/api/rail') {
    res.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' }).end(JSON.stringify(readRail(root)));
    return;
  }
  vite.middlewares(req, res);
});

// One run at a time for the whole repo: each run ends with a git sync.
let active: { run: Run; turnId: string } | null = null;
const clients = new Set<WebSocket>();
const broadcast = (msg: ServerMsg) => { const s = JSON.stringify(msg); for (const c of clients) c.send(s); };
const sendRail = () => broadcast({ type: 'rail', rail: readRail(root) });

const wss = new WebSocketServer({ noServer: true, maxPayload: 64 * 1024 });
http.on('upgrade', (req, socket, head) => {
  if (req.url !== '/mama' || !sameOrigin(req)) { socket.destroy(); return; }
  wss.handleUpgrade(req, socket, head, ws => wss.emit('connection', ws, req));
});

wss.on('connection', ws => {
  clients.add(ws);
  ws.on('close', () => clients.delete(ws));
  ws.send(JSON.stringify({ type: 'rail', rail: readRail(root) } satisfies ServerMsg));
  if (active) ws.send(JSON.stringify({ type: 'busy' } satisfies ServerMsg));
  ws.on('message', data => {
    let msg: ClientMsg;
    try { msg = JSON.parse(String(data)); } catch { return; }
    if (msg.type === 'stop') { active?.run.stop(); return; }
    if (msg.type !== 'prompt' || typeof msg.text !== 'string' || !msg.text.trim()) return;
    if (active) { ws.send(JSON.stringify({ type: 'busy' } satisfies ServerMsg)); return; }
    const turnId = randomUUID();
    broadcast({ type: 'turn_start', turnId, text: msg.text });
    const run = new Run(root, msg.text.trim(), msg.sessionId, {
      onEvent: event => broadcast({ type: 'event', turnId, event }),
      onEnd: (code, stderr, error) => {
        active = null;
        broadcast({ type: 'turn_end', turnId, code, stderr: stderr.slice(-2000), error });
        sendRail(); // the Stop hook has synced and rebuilt books by now
      },
    });
    active = { run, turnId };
  });
});

// Refresh the rail when books are rebuilt outside a run (session start, nightly, another terminal).
let railTimer: NodeJS.Timeout | undefined;
try {
  watch(join(root, 'wiki', 'books'), () => { clearTimeout(railTimer); railTimer = setTimeout(sendRail, 400); });
} catch { /* folder missing until the first build */ }

http.listen(PORT, HOST, () => {
  console.log(`\n  Sales Mama Console → http://localhost:${PORT}\n  repo: ${root}\n  Ctrl+C to stop.\n`);
});

const shutdown = () => { active?.run.stop(); http.close(); void vite.close(); process.exit(0); };
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
