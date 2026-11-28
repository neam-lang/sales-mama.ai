// The voice bridge (voice spec §4, §15): one session per browser socket on /mama/voice.
// Providers are configurable per user: STT and TTS from Inworld, OpenAI or ElevenLabs (cascade), or
// OpenAI Realtime ("GPT live") for hands-free conversation. In every mode the bridge never sends a
// prompt itself: transcripts and GPT's tool calls go to the browser, through the read-back, and on to
// /mama like typed text, so skills, AGENTS.md and the permission settings apply unchanged.
// Privacy (spec §9): no audio or transcript is written to disk or logged. Only the fixed
// acknowledgement phrases are cached, because they contain no user data.
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import type { WebSocket } from 'ws';
import { speakable } from '../../shared/speakable';
import { vocabulary } from '../../shared/mentions';
import {
  ACKS, APPROVAL_REPLY, LIVE_BYE, LIVE_GREETING, LIVE_MORE, LIVE_QUEUED, NAV_PHRASES, MALE_VOICES, PROVIDERS, SPEAKER_RATE, ungroundedNumbers,
  type Provider, type ProviderStatus, type VoiceClientMsg, type VoiceOption, type VoiceServerMsg, type VoiceSettings,
} from '../../shared/voice';
import { BatchStt } from './batch';
import { cleanSettings, keyFile, localDefaults, noKey, readKey } from './config';
import { ElevenTts, elevenTranscribe, listElevenVoices } from './elevenlabs';
import { listVoices, SttSession, synthesise, Tts } from './inworld';
import { OpenAiTts, openAiTranscribe, Realtime } from './openai';
import { sentenceQueue } from './stream';
import type { SpeechStream, SttFactory, SttStream, TtsEngine } from './types';

const CACHE = () => process.env.MAMA_VOICE_CACHE ?? join(homedir(), '.cache', 'sales-mama', 'voice');
/** Cost guards (spec §9): characters synthesised and Realtime minutes per day, for this console. */
const DAILY_CHARS = () => Number(process.env.MAMA_VOICE_DAILY_CHARS ?? 20_000);
const DAILY_LIVE_MIN = () => Number(process.env.MAMA_VOICE_REALTIME_MINUTES ?? 30);
const FIXED = new Set([...Object.values(ACKS), APPROVAL_REPLY, LIVE_GREETING, LIVE_BYE, LIVE_MORE, LIVE_QUEUED, ...Object.values(NAV_PHRASES)]);

const today = () => new Date().toISOString().slice(0, 10);
let usage = { day: '', chars: 0, liveMs: 0 };
const use = () => { if (usage.day !== today()) usage = { day: today(), chars: 0, liveMs: 0 }; return usage; };
function charge(n: number): boolean {
  const u = use();
  if (u.chars + n > DAILY_CHARS()) return false;
  u.chars += n;
  return true;
}

// ---- engines, shared across sockets and rebuilt when a key changes ---------------------------
const ttsCache = new Map<Provider, { key: string; tts: TtsEngine }>();
function ttsFor(p: Provider): TtsEngine | null {
  const key = readKey(p);
  if (!key) return null;
  const c = ttsCache.get(p);
  if (c && c.key === key) return c.tts;
  c?.tts.close();
  const tts = p === 'inworld' ? new Tts(key) : p === 'openai' ? new OpenAiTts(key) : new ElevenTts(key);
  ttsCache.set(p, { key, tts });
  return tts;
}

function sttFor(p: Provider): SttFactory | null {
  const key = readKey(p);
  if (!key) return null;
  if (p === 'inworld') return (mode, o, h) => new SttSession(key, mode, o, h);
  const fn = p === 'openai' ? openAiTranscribe(key) : elevenTranscribe(key);
  return (mode, o, h) => new BatchStt(mode, o, h, fn);
}

const OPENAI_OTHERS: VoiceOption[] = ['alloy', 'coral', 'nova', 'sage', 'shimmer'].map(id => ({ id, name: id[0].toUpperCase() + id.slice(1), gender: '' }));
const voiceCache = new Map<string, Promise<VoiceOption[]>>();
function voicesFor(p: Provider, key: string): Promise<VoiceOption[]> {
  const k = `${p}:${createHash('sha256').update(key).digest('hex').slice(0, 8)}`;
  let v = voiceCache.get(k);
  if (!v) {
    const fallback = MALE_VOICES[p];
    v = (p === 'inworld' ? listVoices(key) : p === 'elevenlabs' ? listElevenVoices(key) : Promise.resolve([...MALE_VOICES.openai, ...OPENAI_OTHERS]))
      .catch(() => fallback);
    voiceCache.set(k, v);
  }
  return v;
}

async function status(): Promise<Record<Provider, ProviderStatus>> {
  const out = {} as Record<Provider, ProviderStatus>;
  await Promise.all(PROVIDERS.map(async p => {
    const key = readKey(p);
    const voices = key ? await Promise.race([voicesFor(p, key), new Promise<VoiceOption[]>(r => setTimeout(() => r(MALE_VOICES[p]), 3000))]) : MALE_VOICES[p];
    out[p] = { available: !!key, stt: true, tts: true, realtime: p === 'openai', keyFile: keyFile(p).replace(homedir(), '~'), voices: voices.slice(0, 400) };
  }));
  return out;
}

function cachePath(provider: Provider, text: string, s: VoiceSettings) {
  const h = createHash('sha256').update(`${provider}|${s.voices[provider]}|${s.rate}|${s.lang}|${text}`).digest('hex').slice(0, 24);
  return join(CACHE(), `${h}.pcm`);
}

export interface BridgeDeps { accounts: () => { id: string; name: string }[] }

export function voiceSession(ws: WebSocket, deps: BridgeDeps) {
  const defaults = localDefaults();
  let settings: VoiceSettings = defaults;
  let stt: SttStream | null = null;
  let live: Realtime | null = null;
  let liveSince = 0;
  let liveTimer: NodeJS.Timeout | undefined;
  let relay: string | null = null;                     // what GPT was told to say next (grounding check)
  let speaking: { id: string; provider: Provider; cancel?: () => void } | null = null;
  let streamed: { id: string; s: SpeechStream; text: string } | null = null;
  const json = (m: VoiceServerMsg) => { if (ws.readyState === ws.OPEN) ws.send(JSON.stringify(m)); };
  const bin = (b: Buffer) => { if (ws.readyState === ws.OPEN && b.length) ws.send(b, { binary: true }); };

  /** Render every fixed phrase once in the chosen voice (in the background), so each one plays instantly. */
  let warming = false;
  async function prewarm() {
    if (warming || process.env.MAMA_VOICE_PREWARM === 'off') return;
    warming = true;
    try {
      for (const text of FIXED) {
        const provider = settings.tts;
        const tts = ttsFor(provider);
        if (!tts || ws.readyState !== ws.OPEN) break;
        const file = cachePath(provider, text, settings);
        if (existsSync(file)) continue;
        try {
          const pcm = await synthesise(tts, text, { voiceId: settings.voices[provider], rate: settings.rate, lang: settings.lang, fast: true });
          mkdirSync(CACHE(), { recursive: true, mode: 0o700 });
          writeFileSync(file, pcm, { mode: 0o600 });
        } catch { break; }                                // no key, rate limit: try again next session
      }
    } finally { warming = false; }
  }

  void status().then(providers => {
    const any = PROVIDERS.some(p => providers[p].available);
    json({ type: 'ready', available: any, providers, defaults, problem: any ? undefined : noKey(defaults.tts) });
    setTimeout(() => void prewarm(), 1500);
  });

  const stopSpeaking = (interrupted: boolean) => {
    if (live) live.stopSpeaking();
    if (!speaking) return;
    const { id, provider, cancel } = speaking;
    speaking = null;
    streamed = null;
    if (cancel) cancel(); else ttsFor(provider)?.cancel(id);
    json({ type: 'speech_end', id, interrupted });
  };

  async function speak(id: string, rawText: string, agent: string | undefined, kind: 'answer' | 'ack' | 'notice') {
    const provider = settings.tts;
    const tts = ttsFor(provider);
    if (!tts) { json({ type: 'voice_error', ...noKey(provider) }); return; }
    stopSpeaking(true);
    // Defence in depth: the browser already made the text speakable; do it again here.
    const text = FIXED.has(rawText) ? rawText : speakable(rawText, kind === 'answer' ? 120 : 40).text;
    if (!text) return;
    speaking = { id, provider };
    json({ type: 'speech_begin', id, text, agent });
    const mine = () => speaking?.id === id;
    const finish = (interrupted: boolean) => { if (mine()) { speaking = null; json({ type: 'speech_end', id, interrupted }); } };
    const playAll = (pcm: Buffer) => { for (let i = 0; i < pcm.length; i += SPEAKER_RATE) bin(pcm.subarray(i, i + SPEAKER_RATE)); };

    const fixed = FIXED.has(text);
    const file = fixed ? cachePath(provider, text, settings) : '';
    if (fixed && existsSync(file)) { playAll(readFileSync(file)); finish(false); return; }   // no network, no cost
    if (!charge(text.length)) {
      finish(true);
      json({ type: 'voice_error', message: 'Voice limit reached for today.', fix: 'Answers stay on screen. Raise MAMA_VOICE_DAILY_CHARS to allow more.' });
      return;
    }
    const opts = { voiceId: settings.voices[provider], rate: settings.rate, lang: settings.lang, fast: fixed };
    if (fixed) {
      try {
        const pcm = await synthesise(tts, text, opts);
        try { mkdirSync(CACHE(), { recursive: true, mode: 0o700 }); writeFileSync(file, pcm, { mode: 0o600 }); } catch { /* cache is optional */ }
        if (!mine()) return;
        playAll(pcm);
        finish(false);
      } catch (err) { finish(true); json({ type: 'voice_error', message: (err as Error).message }); }
      return;
    }
    await tts.speak(id, text, opts, {
      audio: b => { if (mine()) bin(b); },
      words: words => { if (mine()) json({ type: 'words', id, words }); },
      end: (ok, error) => { finish(!ok); if (error) json({ type: 'voice_error', message: error }); },
    });
  }

  /** Live mode: speak an answer while it streams. The first chunk for a new id interrupts what is playing. */
  function sayStream(id: string, text: string, final: boolean, agent?: string) {
    if (!streamed || streamed.id !== id) {
      if (!text.trim() && final) return;
      const provider = settings.tts;
      const tts = ttsFor(provider);
      if (!tts) { json({ type: 'voice_error', ...noKey(provider) }); return; }
      stopSpeaking(true);
      const opts = { voiceId: settings.voices[provider], rate: settings.rate, lang: settings.lang };
      const h = {
        audio: (b: Buffer) => { if (speaking?.id === id) bin(b); },
        words: (w: { w: string; start: number; end: number }[]) => { if (speaking?.id === id) json({ type: 'words', id, words: w }); },
        end: (ok: boolean, error?: string) => {
          if (speaking?.id === id) { speaking = null; streamed = null; json({ type: 'speech_end', id, interrupted: !ok }); }
          if (error) json({ type: 'voice_error', message: error });
        },
      };
      let s: SpeechStream, cancel: (() => void) | undefined;
      if (tts.stream) s = tts.stream(id, opts, h);
      else { const q = sentenceQueue(tts, id, opts, h); s = q; cancel = q.cancel; }
      speaking = { id, provider, cancel };
      streamed = { id, s, text: '' };
      json({ type: 'speech_begin', id, text: '', agent });
    }
    const st = streamed!;
    const clean = FIXED.has(text) ? text : speakable(text, 400).text;
    if (clean) {
      if (!charge(clean.length)) {
        json({ type: 'voice_error', message: 'Voice limit reached for today.', fix: 'Answers stay on screen. Raise MAMA_VOICE_DAILY_CHARS to allow more.' });
        st.s.end();
        return;
      }
      st.text = `${st.text} ${clean}`.trim();
      st.s.push(clean + ' ');
      json({ type: 'speech_text', id, text: st.text });
    }
    if (final) st.s.end();
  }

  function closeLive() {
    if (!live) return;
    const l = live;
    live = null;
    clearTimeout(liveTimer);
    use().liveMs += Date.now() - liveSince;
    l.close();
    json({ type: 'live', on: false });
  }

  function openLive() {
    const key = readKey('openai');
    if (!key) { json({ type: 'voice_error', ...noKey('openai') }); return; }
    const left = DAILY_LIVE_MIN() * 60_000 - use().liveMs;
    if (left <= 0) { json({ type: 'voice_error', message: 'GPT live limit reached for today.', fix: 'Use push-to-talk, or raise MAMA_VOICE_REALTIME_MINUTES.' }); return; }
    closeLive();
    relay = null;
    const session: Realtime = new Realtime(key, settings, {
      started: () => json({ type: 'speech_started' }),
      heard: text => json({ type: 'heard', text }),
      speechBegin: id => json({ type: 'speech_begin', id, text: '', agent: 'mama' }),
      audio: b => bin(b),
      speechText: (id, text) => json({ type: 'speech_text', id, text }),
      speechEnd: (id, interrupted) => json({ type: 'speech_end', id, interrupted }),
      spoken: (_id, transcript) => {
        // Grounding guard: every number GPT says must be in Sales Mama's answer.
        const source = relay;
        relay = null;
        if (source !== null) {
          if (ungroundedNumbers(transcript, source).length) json({ type: 'mismatch', spoken: transcript, source });
        } else if (settings.strict && /\d|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|hundred|thousand)\b/i.test(transcript)) {
          json({ type: 'mismatch', spoken: transcript, source: '' });
        }
      },
      toolPrompt: (callId, prompt) => json({ type: 'tool_prompt', callId, prompt }),
      toolCommand: (callId, command) => { json({ type: 'tool_command', callId, command }); session.commandDone(callId); },
      error: message => json({ type: 'voice_error', message }),
      closed: () => { if (live === session) { live = null; clearTimeout(liveTimer); use().liveMs += Date.now() - liveSince; json({ type: 'live', on: false }); } },
    });
    live = session;
    liveSince = Date.now();
    liveTimer = setTimeout(() => { json({ type: 'voice_error', message: 'GPT live limit reached for today.' }); closeLive(); }, left);
    json({ type: 'live', on: true });
  }

  ws.on('message', (data, isBinary) => {
    if (isBinary) { if (live) live.push(data as Buffer); else stt?.push(data as Buffer); return; }
    let msg: VoiceClientMsg;
    try { msg = JSON.parse(String(data)); } catch { return; }
    switch (msg.type) {
      case 'settings': settings = cleanSettings(settings, msg.settings); setTimeout(() => void prewarm(), 1500); break;
      case 'listen': {
        stt?.cancel(); stt = null;
        const mode = msg.mode === 'tap' || msg.mode === 'conversation' ? msg.mode : 'push';
        if (mode === 'conversation' && settings.engine === 'realtime') { openLive(); break; }
        const factory = sttFor(settings.stt);
        if (!factory) { json({ type: 'voice_error', ...noKey(settings.stt) }); break; }
        const session: SttStream = factory(mode, { lang: settings.lang, prompts: vocabulary(deps.accounts(), ['Sales Mama']) }, {
          started: () => json({ type: 'speech_started' }),
          partial: text => json({ type: 'partial', text }),
          final: text => { json({ type: 'final', text }); if (mode !== 'conversation' && stt === session) stt = null; },
          nothing: () => { json({ type: 'heard_nothing' }); if (stt === session) stt = null; },
          error: message => { json({ type: 'voice_error', message }); if (stt === session) stt = null; },
        });
        stt = session;
        break;
      }
      case 'listen_end': stt?.finish(); break;
      case 'listen_cancel': stt?.cancel(); stt = null; closeLive(); break;
      case 'speak':
        if (typeof msg.id === 'string' && typeof msg.text === 'string' && msg.text.length <= 4000) {
          void speak(msg.id.slice(0, 80), msg.text, typeof msg.agent === 'string' ? msg.agent : undefined, msg.kind === 'ack' || msg.kind === 'notice' ? msg.kind : 'answer');
        }
        break;
      case 'speak_stop': stopSpeaking(true); break;
      case 'say_stream':
        if (typeof msg.id === 'string' && typeof msg.text === 'string' && msg.text.length <= 4000) {
          sayStream(msg.id.slice(0, 80), msg.text, msg.final === true, typeof msg.agent === 'string' ? msg.agent : undefined);
        }
        break;
      case 'tool_result':
        if (live && typeof msg.callId === 'string' && typeof msg.text === 'string') {
          const text = FIXED.has(msg.text) ? msg.text : speakable(msg.text, 120).text || 'Done. The details are on screen.';
          relay = text;
          live.toolResult(msg.callId, text);
        }
        break;
    }
  });
  ws.on('close', () => { stt?.cancel(); stt = null; stopSpeaking(true); closeLive(); });
}
