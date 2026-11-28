// WebSocket bridge to the console server. Holds the chat turns and the rail.
import { useCallback, useEffect, useRef, useState } from 'react';
import { TurnBuilder, parseLines, type Turn } from '../shared/stream';
import type { ClientMsg, Rail, ServerMsg } from '../shared/protocol';

export interface ChatTurn {
  id: string;
  prompt: string;
  turn: Turn;
  text: string;                                   // main agent text, joined
  running: boolean;
  startedAt?: number;                             // ms epoch, for the live timer
  error?: { message: string; fix?: string };
}

const SESSION_KEY = 'mama.session';
const store = {
  get: () => { try { return localStorage.getItem(SESSION_KEY) ?? undefined; } catch { return undefined; } },
  set: (v?: string) => { try { v ? localStorage.setItem(SESSION_KEY, v) : localStorage.removeItem(SESSION_KEY); } catch { /* private mode */ } },
};

export function useBridge() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [rail, setRail] = useState<Rail | null>(null);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>(store.get);
  // One id per conversation, for the local chat history (spec §5.5).
  const [chatId, setChatId] = useState(() => `c-${Date.now().toString(36)}`);
  const ws = useRef<WebSocket | null>(null);
  const builders = useRef(new Map<string, TurnBuilder>());

  // Replay recorded streams: /?replay=mama-day,mama-manager. Add &speed=1 to stream them at a
  // readable pace (demos, design review, motion tests); without it they appear at once.
  const replay = new URLSearchParams(location.search).get('replay');
  const [replaying, setReplaying] = useState(false);
  useEffect(() => {
    if (!replay) return;
    const speed = Number(new URLSearchParams(location.search).get('speed') ?? 0);
    let cancelled = false;
    (async () => {
      const recs = await Promise.all(replay.split(',').map(async name => ({
        name, events: parseLines(await (await fetch(`/api/replay?name=${encodeURIComponent(name)}`)).text()),
      })));
      if (!speed) {
        setTurns(recs.map(({ name, events }) => {
          const b = new TurnBuilder();
          b.applyAll(events);
          return { id: `replay-${name}`, prompt: name.startsWith('mama-') ? `/${name}` : name, turn: { ...b.turn }, text: b.text(), running: false };
        }));
        return;
      }
      setReplaying(true);
      for (const { name, events } of recs) {
        const id = `replay-${name}`, b = new TurnBuilder();
        const fresh: ChatTurn = { id, prompt: name.startsWith('mama-') ? `/${name}` : name, turn: { ...b.turn }, text: '', running: true, startedAt: Date.now() };
        // StrictMode runs this effect twice in development; replace rather than duplicate the turn.
        setTurns(ts => (ts.some(t => t.id === id) ? ts.map(t => (t.id === id ? fresh : t)) : [...ts, fresh]));
        for (const e of events) {
          if (cancelled) return;
          b.apply(e);
          setTurns(ts => ts.map(t => (t.id === id ? { ...t, turn: { ...b.turn }, text: b.text() } : t)));
          await new Promise(r => setTimeout(r, Math.max(4, 28 / speed)));
        }
        setTurns(ts => ts.map(t => (t.id === id ? { ...t, running: false } : t)));
      }
      setReplaying(false);
    })();
    return () => { cancelled = true; };
  }, [replay]);

  // A saved result shown as a chat turn: /?result=company-check/reports/<date>-<uen>.view.md&ask=/company-check%20<uen>
  // (the same cards a live run prints; read through /api/source, so only readable folders).
  const params = new URLSearchParams(location.search);
  const result = params.get('result');
  useEffect(() => {
    if (!result) return;
    fetch(`/api/source?path=${encodeURIComponent(result)}`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then((file: { text: string }) => {
        const b = new TurnBuilder();
        b.apply({ type: 'assistant', message: { id: 'saved-result', content: [{ type: 'text', text: file.text }] } });
        b.apply({ type: 'result', subtype: 'success', is_error: false });
        setTurns([{ id: 'saved-result', prompt: params.get('ask') ?? result, turn: { ...b.turn }, text: b.text(), running: false }]);
      })
      .catch(() => setTurns([]));
  }, [result]);

  useEffect(() => {
    let closed = false;
    let retry: ReturnType<typeof setTimeout>;
    const open = () => {
      const sock = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/mama`);
      ws.current = sock;
      sock.onopen = () => setConnected(true);
      sock.onclose = () => { setConnected(false); if (!closed) retry = setTimeout(open, 1500); };
      sock.onmessage = ev => handle(JSON.parse(ev.data) as ServerMsg);
    };
    open();
    return () => { closed = true; clearTimeout(retry); ws.current?.close(); };
  }, []);

  const update = (id: string, fn: (t: ChatTurn) => ChatTurn) =>
    setTurns(ts => ts.map(t => (t.id === id ? fn(t) : t)));

  function handle(msg: ServerMsg) {
    switch (msg.type) {
      case 'rail': setRail(msg.rail); break;
      case 'busy': setBusy(true); break;
      case 'turn_start': {
        const b = new TurnBuilder();
        builders.current.set(msg.turnId, b);
        setBusy(true);
        setTurns(ts => ts.some(t => t.id === msg.turnId) ? ts
          : [...ts, { id: msg.turnId, prompt: msg.text, turn: b.turn, text: '', running: true, startedAt: Date.now() }]);
        break;
      }
      case 'event': {
        const b = builders.current.get(msg.turnId);
        if (!b) break;
        b.apply(msg.event);
        // New object identities so React re-renders the mutated turn.
        update(msg.turnId, t => ({ ...t, turn: { ...b.turn }, text: b.text() }));
        if (b.turn.sessionId) { setSessionId(b.turn.sessionId); store.set(b.turn.sessionId); }
        break;
      }
      case 'turn_end': {
        setBusy(false);
        const b = builders.current.get(msg.turnId);
        const failed = msg.error ?? (b && !b.turn.result && msg.code !== 0
          ? { message: 'The run stopped before it finished.', fix: 'Try again, or run the same prompt in Claude Code.' } : undefined);
        update(msg.turnId, t => ({ ...t, running: false, error: failed, turn: b ? { ...b.turn } : t.turn }));
        break;
      }
    }
  }

  const send = useCallback((m: ClientMsg) => ws.current?.readyState === WebSocket.OPEN && ws.current.send(JSON.stringify(m)), []);

  const ask = useCallback((text: string, voice = false) => {
    if (!text.trim()) return;
    send({ type: 'prompt', text: text.trim(), sessionId, ...(voice ? { voice: true } : {}) });
  }, [send, sessionId]);

  const stop = useCallback(() => send({ type: 'stop' }), [send]);

  const newChat = useCallback(() => {
    store.set(undefined);
    setSessionId(undefined);
    setTurns([]);
    setChatId(`c-${Date.now().toString(36)}`);
  }, []);

  /** Reopen a conversation from the local history; the next prompt resumes its Claude session. */
  const loadChat = useCallback((c: { id: string; sessionId?: string; turns: ChatTurn[] }) => {
    store.set(c.sessionId);
    setSessionId(c.sessionId);
    setTurns(c.turns.map(t => ({ ...t, running: false })));
    setChatId(c.id);
  }, []);

  return { turns, rail, connected, busy: busy || !!replay || !!result, replay: !!replay, replaying, saved: !!result, sessionId, chatId, ask, stop, newChat, loadChat };
}
