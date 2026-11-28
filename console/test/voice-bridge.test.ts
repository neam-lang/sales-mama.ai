// The voice bridge against a mock Inworld (no key, no network): TTS streaming, word timings,
// barge-in cancel, the cached acknowledgement, push-to-talk STT, the cost guard, and privacy.
import { createServer, type Server } from 'node:http';
import { mkdtempSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import WebSocket, { WebSocketServer } from 'ws';
import type { VoiceServerMsg } from '../shared/voice';

interface Seen { tts: any[]; stt: any[]; sttAudioBytes: number; auth: string[] }
const seen: Seen = { tts: [], stt: [], sttAudioBytes: 0, auth: [] };
let mock: Server, bridge: Server, bridgePort = 0;
const cache = mkdtempSync(join(tmpdir(), 'mama-voice-cache-'));

beforeAll(async () => {
  // --- mock Inworld: voices over HTTP, TTS and STT over WebSocket
  mock = createServer((req, res) => {
    seen.auth.push(String(req.headers.authorization));
    res.writeHead(200, { 'content-type': 'application/json' }).end(JSON.stringify({ voices: [{ voiceId: 'Luna', displayName: 'Luna', languages: ['en'] }] }));
  });
  const mwss = new WebSocketServer({ server: mock });
  mwss.on('connection', (ws, req) => {
    seen.auth.push(String(req.headers.authorization));
    if (req.url?.startsWith('/tts/')) {
      ws.on('message', d => {
        const m = JSON.parse(String(d));
        seen.tts.push(m);
        const id = m.contextId;
        if (m.closeContext) {
          const audio = Buffer.alloc(4800, 1).toString('base64');         // 0.1 s at 24 kHz
          const send = (o: object) => ws.send(JSON.stringify({ result: { contextId: id, ...o } }));
          setTimeout(() => {
            send({ audioChunk: { audioContent: audio, timestampInfo: { wordAlignment: { words: ['You', ' ', 'have'], wordStartTimeSeconds: [0, 0.05, 0.06], wordEndTimeSeconds: [0.05, 0.06, 0.1] } } } });
            send({ flushCompleted: {} });
            send({ audioChunk: { audioContent: audio, timestampInfo: { wordAlignment: { words: ['three.'], wordStartTimeSeconds: [0.01], wordEndTimeSeconds: [0.09] } } } });
            setTimeout(() => send({ contextClosed: {} }), 60);
          }, 10);
        }
        if (m.cancelContext) ws.send(JSON.stringify({ result: { contextId: id, contextClosed: {} } }));
      });
    } else {
      ws.on('message', (d, bin) => {
        if (bin) { seen.sttAudioBytes += (d as Buffer).length; return; }
        const m = JSON.parse(String(d));
        seen.stt.push(m);
        if (m.closeStream) setTimeout(() => ws.send(JSON.stringify({ result: { transcription: { transcript: 'Brief me on Kestrel Physio.', isFinal: true } } })), 20);
        if (m.transcribeConfig) ws.send(JSON.stringify({ result: { speechStarted: { startTimeMs: 0 } } }));
      });
    }
  });
  await new Promise<void>(r => mock.listen(0, '127.0.0.1', () => r()));
  const mp = (mock.address() as { port: number }).port;
  process.env.MAMA_INWORLD_WS = `ws://127.0.0.1:${mp}`;
  process.env.MAMA_INWORLD_HTTP = `http://127.0.0.1:${mp}`;
  process.env.INWORLD_API_KEY = 'test-key';
  process.env.MAMA_VOICE_CACHE = cache;
  process.env.MAMA_VOICE_DAILY_CHARS = '400';
  process.env.MAMA_CONFIG_DIR = mkdtempSync(join(tmpdir(), 'mama-voice-config-'));   // never the real ~/.config
  delete process.env.OPENAI_API_KEY; delete process.env.ELEVENLABS_API_KEY;

  // --- the bridge under test (imported after env is set)
  const { voiceSession } = await import('../server/voice/bridge');
  bridge = createServer();
  const wss = new WebSocketServer({ server: bridge });
  wss.on('connection', ws => voiceSession(ws, { accounts: () => [{ id: 'kestrel-physio', name: 'Kestrel Physio Pte Ltd' }] }));
  await new Promise<void>(r => bridge.listen(0, '127.0.0.1', () => r()));
  bridgePort = (bridge.address() as { port: number }).port;
});

afterAll(() => { mock.close(); bridge.close(); });

function client() {
  const ws = new WebSocket(`ws://127.0.0.1:${bridgePort}`);
  const msgs: VoiceServerMsg[] = [];
  const audio: Buffer[] = [];
  ws.on('message', (d, bin) => (bin ? audio.push(d as Buffer) : msgs.push(JSON.parse(String(d)))));
  const until = async (pred: () => boolean, ms = 2000) => {
    const t = Date.now();
    while (!pred()) { if (Date.now() - t > ms) throw new Error(`timeout; got ${JSON.stringify(msgs.map(m => m.type))}`); await new Promise(r => setTimeout(r, 10)); }
  };
  const open = new Promise<void>(r => ws.on('open', () => r()));
  return { ws, msgs, audio, until, open, send: (o: object) => ws.send(JSON.stringify(o)) };
}

describe('voice bridge (mock Inworld)', () => {
  it('says it is ready and lists voices; the key stays server-side', async () => {
    const c = client(); await c.open;
    await c.until(() => c.msgs.some(m => m.type === 'ready'));
    const r = c.msgs.find(m => m.type === 'ready') as Extract<VoiceServerMsg, { type: 'ready' }>;
    expect(r.available).toBe(true);
    expect(r.providers.inworld.available).toBe(true);
    expect(r.providers.openai.available).toBe(false);
    expect(r.providers.inworld.voices[0].id).toBe('Luna');
    expect(r.defaults.voices.inworld).toBe('Junhao');                   // male by default
    expect(JSON.stringify(c.msgs)).not.toContain('test-key');
    expect(seen.auth.every(a => a === 'Basic test-key')).toBe(true);
    c.ws.close();
  });

  it('streams an answer: begin, audio, words with flush offsets, end', async () => {
    const c = client(); await c.open;
    c.send({ type: 'speak', id: 't1', text: 'You have **three** meetings. See `wiki/books/praveen.json`.', kind: 'answer' });
    await c.until(() => c.msgs.some(m => m.type === 'speech_end'));
    const begin = c.msgs.find(m => m.type === 'speech_begin') as any;
    expect(begin.text).toBe('You have three meetings. See.');
    expect(c.audio.reduce((n, b) => n + b.length, 0)).toBe(9600);
    const words = c.msgs.filter(m => m.type === 'words').flatMap((m: any) => m.words);
    expect(words.map((w: any) => w.w)).toEqual(['You', 'have', 'three.']);
    expect(words[2].start).toBeCloseTo(0.11, 2);                       // 0.1 s flush base + 0.01
    const create = seen.tts.find(m => m.contextId === 't1' && m.create);
    expect(create.create).toMatchObject({ modelId: 'inworld-tts-2', timestampType: 'WORD', audioConfig: { audioEncoding: 'PCM', sampleRateHertz: 24000 } });
    expect((c.msgs.find(m => m.type === 'speech_end') as any).interrupted).toBe(false);
    c.ws.close();
  });

  it('barge-in cancels the Inworld context', async () => {
    const c = client(); await c.open;
    c.send({ type: 'speak', id: 't2', text: 'A long answer that will be interrupted.' });
    await c.until(() => c.msgs.some(m => m.type === 'speech_begin'));
    c.send({ type: 'speak_stop' });
    await c.until(() => c.msgs.some(m => m.type === 'speech_end'));
    expect((c.msgs.find(m => m.type === 'speech_end') as any).interrupted).toBe(true);
    await new Promise(r => setTimeout(r, 50));
    expect(seen.tts.some(m => m.contextId === 't2' && m.cancelContext)).toBe(true);
    c.ws.close();
  });

  it('caches fixed acknowledgements: the second one makes no Inworld request', async () => {
    const c = client(); await c.open;
    c.send({ type: 'speak', id: 'a1', text: 'Pulling the brief.', kind: 'ack' });
    await c.until(() => c.msgs.filter(m => m.type === 'speech_end').length === 1);
    const before = seen.tts.length;
    c.send({ type: 'speak', id: 'a2', text: 'Pulling the brief.', kind: 'ack' });
    await c.until(() => c.msgs.filter(m => m.type === 'speech_end').length === 2);
    expect(seen.tts.length).toBe(before);
    expect(seen.tts.find(m => m.create && m.create.modelId === 'inworld-tts-2-flash')).toBeTruthy();
    c.ws.close();
  });

  it('push-to-talk: audio relayed, closeStream on release, one final with account vocabulary', async () => {
    const c = client(); await c.open;
    c.send({ type: 'listen', mode: 'push' });
    await new Promise(r => setTimeout(r, 30));
    for (let i = 0; i < 5; i++) c.ws.send(Buffer.alloc(3200));
    c.send({ type: 'listen_end' });
    await c.until(() => c.msgs.some(m => m.type === 'final'));
    expect((c.msgs.find(m => m.type === 'final') as any).text).toBe('Brief me on Kestrel Physio.');
    expect(seen.sttAudioBytes).toBe(16000);
    const cfg = seen.stt.find(m => m.transcribeConfig);
    expect(cfg.audioProtocol).toBe('BINARY');
    expect(cfg.transcribeConfig).toMatchObject({ audioEncoding: 'LINEAR16', sampleRateHertz: 16000, inworldSttV1Config: { vadThreshold: 0 } });
    expect(cfg.transcribeConfig.prompts).toEqual(['Sales Mama', 'Kestrel Physio']);
    expect(seen.stt.some(m => m.closeStream)).toBe(true);
    c.ws.close();
  });

  it('stops at the daily character cap and says so', async () => {
    const c = client(); await c.open;
    c.send({ type: 'speak', id: 'big', text: 'word '.repeat(100).trim() + '.' });
    await c.until(() => c.msgs.some(m => m.type === 'voice_error'));
    expect((c.msgs.find(m => m.type === 'voice_error') as any).message).toMatch(/limit/i);
    c.ws.close();
  });

  it('writes no audio to disk except fixed phrases', () => {
    const files = readdirSync(cache);
    expect(files.length).toBe(1);                                      // the one cached acknowledgement
    expect(files[0]).toMatch(/^[0-9a-f]{24}\.pcm$/);
  });
});
