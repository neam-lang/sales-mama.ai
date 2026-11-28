// Inworld clients (voice spec §3): speech-to-text and text-to-speech over WebSocket, server to
// server. The key never reaches the browser. MAMA_INWORLD_WS points both at a mock in tests.
import WebSocket from 'ws';
import { MALE_VOICES, MIC_RATE, SPEAKER_RATE, type VoiceMode, type VoiceOption, type Word } from '../../shared/voice';
import type { SpeakHandlers, SpeakOpts, SttHandlers, SttOpts, SttStream, TtsEngine } from './types';

const WS_BASE = () => process.env.MAMA_INWORLD_WS ?? 'wss://api.inworld.ai';
const HTTP_BASE = () => process.env.MAMA_INWORLD_HTTP ?? 'https://api.inworld.ai';

export const MODELS = { answer: 'inworld-tts-2', ack: 'inworld-tts-2-flash', stt: 'inworld/inworld-stt-1' } as const;

const auth = (key: string) => ({ headers: { Authorization: `Basic ${key}` } });

function explainStatus(code: number | undefined, message?: string): string {
  if (code === 16 || code === 7) return 'Inworld refused the API key. Check the key in ~/.config/sales-mama/inworld.json.';
  if (code === 8) return 'Inworld rate limit reached. Try again in a moment.';
  return `Inworld error${code ? ` ${code}` : ''}${message ? `: ${message}` : ''}`;
}

// ---------------------------------------------------------------------------------------------
// Text to speech: one persistent socket, one context per speech, cancelContext on barge-in.
// ---------------------------------------------------------------------------------------------
interface Ctx { h: SpeakHandlers; samples: number; flushBase: number; ended: boolean }

export class Tts implements TtsEngine {
  private ws: WebSocket | null = null;
  private opening: Promise<WebSocket> | null = null;
  private ctxs = new Map<string, Ctx>();
  constructor(private key: string) {}

  private connect(): Promise<WebSocket> {
    if (this.ws?.readyState === WebSocket.OPEN) return Promise.resolve(this.ws);
    if (this.opening) return this.opening;
    this.opening = new Promise((resolve, reject) => {
      const ws = new WebSocket(`${WS_BASE()}/tts/v1/voice:streamBidirectional`, auth(this.key));
      ws.on('open', () => { this.ws = ws; this.opening = null; resolve(ws); });
      ws.on('unexpected-response', (_q, res) => { this.opening = null; reject(new Error(res.statusCode === 401 ? explainStatus(16) : `Inworld TTS HTTP ${res.statusCode}`)); });
      ws.on('error', err => { this.opening = null; reject(err); });
      ws.on('message', data => this.onMessage(String(data)));
      ws.on('close', () => {
        if (this.ws === ws) this.ws = null;
        for (const [id, c] of this.ctxs) { this.ctxs.delete(id); if (!c.ended) { c.ended = true; c.h.end(false, 'The voice connection closed.'); } }
      });
    });
    return this.opening;
  }

  private onMessage(raw: string) {
    let m: any;
    try { m = JSON.parse(raw); } catch { return; }
    const r = m.result ?? m;
    const c = r.contextId ? this.ctxs.get(r.contextId) : undefined;
    if (!c) return;                                    // a cancelled context's late chunks are dropped
    if (r.status?.code) { this.finish(r.contextId, false, explainStatus(r.status.code, r.status.message)); return; }
    const chunk = r.audioChunk;
    if (chunk?.audioContent) {
      const pcm = Buffer.from(chunk.audioContent, 'base64');
      const wa = chunk.timestampInfo?.wordAlignment;
      if (wa?.words?.length) {
        const words: Word[] = [];
        wa.words.forEach((w: string, i: number) => {
          const t = w.trim();
          if (!t) return;
          const end = c.flushBase + (wa.wordEndTimeSeconds?.[i] ?? 0);
          // Punctuation arrives as its own token ("day", "."); attach it to the word before.
          if (/^[.,!?;:…)"'’]+$/.test(t) && words.length) { words[words.length - 1].w += t; words[words.length - 1].end = end; return; }
          words.push({ w: t, start: c.flushBase + (wa.wordStartTimeSeconds?.[i] ?? 0), end });
        });
        if (words.length) c.h.words(words);
      }
      c.samples += pcm.length / 2;
      c.h.audio(pcm);
    }
    if (r.flushCompleted) c.flushBase = c.samples / SPEAKER_RATE;   // timestamps restart after each flush
    if (r.contextClosed) this.finish(r.contextId, true);
  }

  private finish(id: string, ok: boolean, error?: string) {
    const c = this.ctxs.get(id);
    if (!c) return;
    this.ctxs.delete(id);
    if (!c.ended) { c.ended = true; c.h.end(ok, error); }
  }

  async speak(id: string, text: string, o: SpeakOpts, h: SpeakHandlers): Promise<void> {
    const st = this.stream(id, o, h);
    st.push(text);
    st.end();
  }

  /** One context per answer; text is pushed as it streams and Inworld finds the sentence boundaries. */
  stream(id: string, o: SpeakOpts, h: SpeakHandlers) {
    this.ctxs.set(id, { h, samples: 0, flushBase: 0, ended: false });
    const pending: object[] = [];
    let ws: WebSocket | null = null;
    const send = (msg: object) => { const m = { contextId: id, ...msg }; if (ws) ws.send(JSON.stringify(m)); else pending.push(m); };
    send({ create: { voiceId: o.voiceId, modelId: o.modelId ?? (o.fast ? MODELS.ack : MODELS.answer), ...(o.lang && o.lang !== 'auto' ? { language: o.lang } : {}),
      audioConfig: { audioEncoding: 'PCM', sampleRateHertz: SPEAKER_RATE, speakingRate: o.rate }, timestampType: 'WORD',
      autoMode: true, autoModeStrategy: 'SENTENCE_BOUNDARY' } });
    this.connect().then(sock => {
      if (!this.ctxs.has(id)) return;                  // cancelled while connecting
      ws = sock;
      for (const m of pending.splice(0)) sock.send(JSON.stringify(m));
    }, e => this.finish(id, false, (e as Error).message));
    // Steering (TTS-2 only): the instruction stays in force for the whole context, so it is sent once, first.
    let steer = o.style && !(o.fast && !o.modelId) ? `[${o.style}] ` : '';
    return {
      push: (raw: string) => {
        const text = steer + raw;
        steer = '';
        for (let i = 0; i < text.length; i += 1800) send({ sendText: { text: text.slice(i, i + 1800) } });
      },
      end: () => send({ closeContext: {} }),
    };
  }

  /** Stop now: the server aborts synthesis and stops billing for the rest. */
  cancel(id: string) {
    const c = this.ctxs.get(id);
    if (!c) return;
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ contextId: id, cancelContext: {} }));
    this.finish(id, false);
  }

  close() { this.ws?.close(); }
}

/** Synthesise a fixed phrase in one go with any provider (acknowledgements, which are then cached). */
export function synthesise(tts: TtsEngine, text: string, o: SpeakOpts): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const parts: Buffer[] = [];
    tts.speak(`phrase-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`, text, o, {
      audio: b => parts.push(b), words: () => {}, end: (ok, err) => (ok ? resolve(Buffer.concat(parts)) : reject(new Error(err ?? 'synthesis failed'))),
    });
  });
}

// ---------------------------------------------------------------------------------------------
// Speech to text: one socket per listening session.
// push: manual turn (vadThreshold 0), finished by closeStream on release.
// tap: Inworld turn detection, the first final ends it.
// conversation: Inworld turn detection, every final is a turn, until cancelled.
// ---------------------------------------------------------------------------------------------
export class SttSession implements SttStream {
  private ws: WebSocket;
  private open = false;
  private queue: Buffer[] = [];
  private finals: string[] = [];
  private done = false;
  private finishTimer?: NodeJS.Timeout;
  private silenceTimer?: NodeJS.Timeout;
  private heard = false;
  private finishing = false;

  constructor(key: string, private mode: VoiceMode, opts: SttOpts, private h: SttHandlers) {
    this.ws = new WebSocket(`${WS_BASE()}/stt/v1/transcribe:streamBidirectional`, auth(key));
    this.ws.on('open', () => {
      const manual = mode === 'push';
      this.ws.send(JSON.stringify({
        transcribeConfig: {
          modelId: MODELS.stt, audioEncoding: 'LINEAR16', sampleRateHertz: MIC_RATE, numberOfChannels: 1,
          ...(opts.lang && opts.lang !== 'auto' ? { language: opts.lang } : {}),
          ...(opts.prompts?.length ? { prompts: opts.prompts } : {}),
          // Live conversation: wait for a real end of turn, not the pause at a comma (found in the live test).
          ...(mode === 'conversation' ? { endOfTurnConfidenceThreshold: 0.6 } : {}),
          inworldSttV1Config: manual ? { vadThreshold: 0 } : mode === 'tap' ? { maxTurnSilence: 900 } : { minEndOfTurnSilenceWhenConfident: 700, maxTurnSilence: 1400 },
        },
        audioProtocol: 'BINARY',
      }));
      this.open = true;
      for (const b of this.queue) this.ws.send(b);
      this.queue = [];
    });
    this.ws.on('message', d => this.onMessage(String(d)));
    this.ws.on('unexpected-response', (_q, res) => this.fail(res.statusCode === 401 ? explainStatus(16) : `Inworld STT HTTP ${res.statusCode}`));
    this.ws.on('error', e => this.fail(e.message));
    this.ws.on('close', () => this.settle());
    if (mode !== 'push') this.silenceTimer = setTimeout(() => { if (!this.heard) this.finish(); }, 8000);
  }

  private onMessage(raw: string) {
    let m: any;
    try { m = JSON.parse(raw); } catch { return; }
    const r = m.result ?? m;
    if (r.status?.code) { this.fail(explainStatus(r.status.code, r.status.message)); return; }
    if (r.speechStarted) { this.heard = true; this.h.started(); }
    const tr = r.transcription;
    if (!tr) return;
    const text = String(tr.transcript ?? '').trim();
    if (!tr.isFinal) { if (text) this.h.partial([...this.finals, text].join(' ')); return; }
    if (!text) return;
    if (this.mode === 'conversation') { this.h.final(text); return; }
    this.finals.push(text);
    if (this.mode === 'tap' || this.finishing) { this.settle(); this.ws.close(); }
  }

  push(pcm: Buffer) {
    if (this.done) return;
    if (this.open) this.ws.send(pcm); else if (this.queue.length < 300) this.queue.push(pcm);
  }

  /** Finish the turn: flush, then wait (at most 3 s) for the final transcript. */
  finish() {
    if (this.done || this.finishing) return;
    this.finishing = true;
    clearTimeout(this.silenceTimer);
    const close = () => { if (this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ closeStream: {} })); };
    if (this.open) close(); else this.ws.once('open', close);
    this.finishTimer = setTimeout(() => { this.settle(); this.ws.terminate(); }, 3000);
  }

  cancel() {
    this.done = true;
    clearTimeout(this.silenceTimer); clearTimeout(this.finishTimer);
    this.ws.terminate();
  }

  private settle() {
    if (this.done) return;
    this.done = true;
    clearTimeout(this.silenceTimer); clearTimeout(this.finishTimer);
    if (this.mode === 'conversation') { this.h.nothing(); return; }   // the stream ended: the bridge reopens it
    const text = this.finals.join(' ').trim();
    if (text) this.h.final(text); else this.h.nothing();
  }

  private fail(msg: string) {
    if (this.done) return;
    this.done = true;
    clearTimeout(this.silenceTimer); clearTimeout(this.finishTimer);
    this.h.error(msg);
    this.ws.terminate();
  }
}

/** Stock and custom voices for the picker. Custom voices (your clones) come first, then measured male voices. */
export async function listVoices(key: string): Promise<VoiceOption[]> {
  const r = await fetch(`${HTTP_BASE()}/tts/v1/voices`, { headers: { Authorization: `Basic ${key}` } });
  if (!r.ok) throw new Error(r.status === 401 ? explainStatus(16) : `Inworld voices HTTP ${r.status}`);
  const d = await r.json() as { voices?: { voiceId: string; displayName?: string; languages?: string[]; isCustom?: boolean; tags?: string[] }[] };
  const male = new Map(MALE_VOICES.inworld.map(v => [v.id, v]));
  return (d.voices ?? []).map(v => ({
    id: v.voiceId, name: v.displayName ?? v.voiceId, langs: v.languages ?? [],
    gender: male.has(v.voiceId) ? 'male' as const : '' as const,
    note: v.isCustom ? 'your custom voice' : male.get(v.voiceId)?.note ?? (v.tags ?? []).slice(0, 3).join(', '),
  }));
}
