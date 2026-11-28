// Voice state for the console (spec §4.3, §5, §15). Talks to /mama/voice. Transcripts (cascade) and
// GPT's tool calls (realtime) go back to the app, which puts them through the read-back and sends
// them on /mama like typed text.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  DEFAULT_SETTINGS, mergeSettings,
  type Provider, type ProviderStatus, type VoiceClientMsg, type VoiceMode, type VoiceServerMsg, type VoiceSettings, type Word,
} from '../../shared/voice';
import { earcon, Mic, Player } from './audio';

export type MicState = 'idle' | 'listening' | 'hearing';
export interface Caption { id: string; text: string; words: Word[]; agent?: string }
/** Only what the user changed is stored, so machine defaults (e.g. your own cloned voice) still apply. */
interface Prefs { speakAnswers: boolean; overrides: Partial<VoiceSettings> }

const PREFS_KEY = 'mama.voice';
const loadPrefs = (): Prefs => {
  try {
    const p = JSON.parse(localStorage.getItem(PREFS_KEY) ?? '{}');
    return { speakAnswers: p.speakAnswers === true, overrides: p.overrides && typeof p.overrides === 'object' ? p.overrides : {} };
  } catch { return { speakAnswers: false, overrides: {} }; }
};

/** Conversation mode stops itself after 2 minutes without speech (spec §9, bystanders). */
const IDLE_MS = 120_000;
/** Ignore "speech started" in the first 250 ms of our own audio (echo gate, spec §14). */
const ECHO_GATE_MS = 250;

export interface VoiceHandlers {
  onFinal(text: string, mode: VoiceMode): void;
  onToolPrompt(callId: string, prompt: string): void;
  onCommand(command: string): void;
}

export function useVoice(handlers: VoiceHandlers) {
  const [prefs, setPrefs] = useState<Prefs>(loadPrefs);
  const [defaults, setDefaults] = useState<VoiceSettings>(DEFAULT_SETTINGS);
  const [available, setAvailable] = useState<boolean | null>(null);
  const [problem, setProblem] = useState<{ message: string; fix?: string } | null>(null);
  const [providers, setProviders] = useState<Record<Provider, ProviderStatus> | null>(null);
  const [mic, setMic] = useState<MicState>('idle');
  const [mode, setMode] = useState<VoiceMode | null>(null);
  const [partial, setPartial] = useState('');
  const [heard, setHeard] = useState('');
  const [caption, setCaption] = useState<Caption | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const [live, setLive] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const settings = useMemo(() => mergeSettings(defaults, prefs.overrides), [defaults, prefs.overrides]);
  const ws = useRef<WebSocket | null>(null);
  const player = useRef(new Player());
  const micRef = useRef<Mic | null>(null);
  const modeRef = useRef<VoiceMode | null>(null);
  const h = useRef(handlers);
  h.current = handlers;
  const speechId = useRef<string | null>(null);
  const speechStartedAt = useRef(0);
  const last = useRef<{ text: string; agent?: string } | null>(null);
  const streamId = useRef<string | null>(null);
  const idle = useRef<ReturnType<typeof setTimeout>>();
  const errTimer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => { try { localStorage.setItem(PREFS_KEY, JSON.stringify(prefs)); } catch { /* private mode */ } }, [prefs]);

  const send = useCallback((m: VoiceClientMsg) => { if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(m)); }, []);
  const flashError = useCallback((msg: string) => {
    setError(msg);
    clearTimeout(errTimer.current);
    errTimer.current = setTimeout(() => setError(null), 7000);
  }, []);

  const stopSpeaking = useCallback(() => {
    player.current.stop();
    if (speechId.current) send({ type: 'speak_stop' });
    speechId.current = null;
    setSpeaking(false);
    setCaption(null);
  }, [send]);

  const closeMic = useCallback(async () => {
    clearTimeout(idle.current);
    modeRef.current = null;
    setMode(null);
    setMic('idle');
    setPartial('');
    await micRef.current?.stop();
  }, []);

  const armIdle = useCallback(() => {
    clearTimeout(idle.current);
    if (modeRef.current === 'conversation') idle.current = setTimeout(() => { send({ type: 'listen_cancel' }); void closeMic(); earcon('close'); }, IDLE_MS);
  }, [send, closeMic]);

  useEffect(() => {
    let closed = false;
    let retry: ReturnType<typeof setTimeout>;
    player.current.onIdle = () => { if (speechId.current === null) { setSpeaking(false); setCaption(null); } };
    const open = () => {
      const sock = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/mama/voice`);
      sock.binaryType = 'arraybuffer';
      ws.current = sock;
      sock.onopen = () => sock.send(JSON.stringify({ type: 'settings', settings: loadPrefs().overrides } satisfies VoiceClientMsg));
      sock.onclose = () => { setLive(false); if (!closed) retry = setTimeout(open, 2000); };
      sock.onmessage = ev => {
        if (ev.data instanceof ArrayBuffer) { if (speechId.current) player.current.push(ev.data); return; }
        const m = JSON.parse(ev.data) as VoiceServerMsg;
        switch (m.type) {
          case 'ready': setAvailable(m.available); setProblem(m.problem ?? null); setProviders(m.providers); setDefaults(m.defaults); break;
          case 'speech_started':
            setMic(s => (s === 'idle' ? s : 'hearing'));
            armIdle();
            // Barge-in: the user talks over the voice, so it stops at once.
            if (modeRef.current === 'conversation' && speechId.current && performance.now() - speechStartedAt.current > ECHO_GATE_MS) stopSpeaking();
            break;
          case 'partial': setPartial(m.text); setMic(s => (s === 'idle' ? s : 'hearing')); break;
          case 'heard': setHeard(m.text); setPartial(''); armIdle(); break;
          case 'final': {
            const md = modeRef.current ?? 'push';
            setPartial('');
            if (md === 'conversation') { setMic('listening'); armIdle(); } else void closeMic();
            earcon('close');
            h.current.onFinal(m.text, md);
            break;
          }
          case 'heard_nothing': if (modeRef.current !== 'conversation') void closeMic(); break;
          case 'speech_begin':
            speechId.current = m.id;
            speechStartedAt.current = performance.now();
            player.current.begin();
            setSpeaking(true);
            setCaption({ id: m.id, text: m.text, words: [], agent: m.agent });
            break;
          case 'speech_text': setCaption(c => (c && c.id === m.id ? { ...c, text: m.text } : c)); break;
          case 'words': setCaption(c => (c && c.id === m.id ? { ...c, words: [...c.words, ...m.words] } : c)); break;
          case 'speech_end':
            if (speechId.current === m.id) {
              speechId.current = null;
              player.current.end();
              if (m.interrupted) { player.current.stop(); setSpeaking(false); setCaption(null); }
            }
            break;
          case 'tool_prompt': h.current.onToolPrompt(m.callId, m.prompt); break;
          case 'tool_command': h.current.onCommand(m.command); break;
          case 'mismatch':
            flashError(m.source ? 'GPT said a number that is not in Sales Mama’s answer. Trust the card on screen.' : 'GPT answered on its own, without Sales Mama. Trust only what is on screen.');
            break;
          case 'live':
            setLive(m.on);
            if (!m.on && modeRef.current === 'conversation') void closeMic();
            break;
          case 'voice_error':
            flashError(m.fix ? `${m.message} ${m.fix}` : m.message);
            if (modeRef.current !== 'conversation') void closeMic();
            break;
        }
      };
    };
    open();
    return () => { closed = true; clearTimeout(retry); ws.current?.close(); player.current.stop(); void micRef.current?.stop(); };
  }, [armIdle, closeMic, flashError, stopSpeaking]);

  /** Open the mic for one turn ('push' until released, 'tap' until the end is heard) or a conversation. */
  const listen = useCallback(async (m: VoiceMode) => {
    if (available === false) { flashError(problem ? `${problem.message} ${problem.fix ?? ''}` : 'Voice is not available.'); return; }
    stopSpeaking();
    micRef.current ??= new Mic(pcm => ws.current?.readyState === WebSocket.OPEN && ws.current.send(pcm));
    modeRef.current = m;
    setMode(m);
    setMic('listening');
    setPartial('');
    setHeard('');
    send({ type: 'listen', mode: m });
    earcon('open');
    try { await micRef.current.start(); }
    catch (e) {
      send({ type: 'listen_cancel' });
      void closeMic();
      earcon('error');
      flashError((e as Error).name === 'NotAllowedError' ? 'Microphone access was blocked. Allow it in the browser’s site settings.' : `Microphone unavailable: ${(e as Error).message}`);
      return;
    }
    armIdle();
  }, [available, problem, send, stopSpeaking, closeMic, armIdle, flashError]);

  /** Push-to-talk released: finish the turn. */
  const release = useCallback(async () => {
    if (modeRef.current !== 'push') return;
    await micRef.current?.stop();                  // flushes the last chunk first
    send({ type: 'listen_end' });
    setMic(s => (s === 'idle' ? s : 'hearing'));
  }, [send]);

  const cancelListen = useCallback(() => {
    if (!modeRef.current) return;
    send({ type: 'listen_cancel' });
    void closeMic();
  }, [send, closeMic]);

  const toggleConversation = useCallback(() => {
    if (modeRef.current === 'conversation') { cancelListen(); earcon('close'); }
    else void listen('conversation');
  }, [cancelListen, listen]);

  const said = useRef(new Map<string, number>());
  const say = useCallback((text: string, kind: 'answer' | 'ack' | 'notice' = 'answer', id?: string, agent?: string) => {
    if (!text.trim() || available === false) return;
    // The same answer is spoken once, even if it is asked for twice.
    if (id) { const t = said.current.get(id); if (t && Date.now() - t < 10_000) return; said.current.set(id, Date.now()); }
    if (kind === 'answer') last.current = { text, agent };
    send({ type: 'speak', id: id ?? `s-${Date.now().toString(36)}`, text, agent, kind });
  }, [available, send]);

  /** Live mode: speak an answer while it streams (one id per answer; `final` closes it). */
  const sayStream = useCallback((id: string, text: string, final: boolean, agent?: string) => {
    if (available === false) return;
    if (text) last.current = { text: last.current && streamId.current === id ? `${last.current.text} ${text}` : text, agent };
    streamId.current = id;
    send({ type: 'say_stream', id, text, final, agent });
  }, [available, send]);

  /** Realtime: hand Sales Mama's answer back to GPT to speak. */
  const toolResult = useCallback((callId: string, text: string) => {
    last.current = { text };
    send({ type: 'tool_result', callId, text });
  }, [send]);

  const repeat = useCallback(() => { if (last.current) say(last.current.text, 'answer', undefined, last.current.agent); }, [say]);

  const setSpeakAnswers = useCallback((on: boolean) => {
    setPrefs(p => ({ ...p, speakAnswers: on }));
    if (!on) stopSpeaking();
  }, [stopSpeaking]);

  const setSettings = useCallback((s: Partial<VoiceSettings>) => {
    setPrefs(p => {
      const overrides = { ...p.overrides, ...s, ...(s.voices ? { voices: { ...(p.overrides.voices ?? {}), ...s.voices } as VoiceSettings['voices'] } : {}) };
      send({ type: 'settings', settings: overrides });
      return { ...p, overrides };
    });
  }, [send]);

  const resetSettings = useCallback(() => {
    setPrefs(p => ({ ...p, overrides: {} }));
    send({ type: 'settings', settings: defaults });
  }, [send, defaults]);

  const level = useCallback(() => (speaking ? player.current.level() * 3 : (micRef.current?.level ?? 0) * 6), [speaking]);
  const clock = useCallback(() => player.current.clock(), []);

  return {
    available, problem, providers, error, mic, mode, partial, heard, caption, speaking, live,
    speakAnswers: prefs.speakAnswers, settings, defaults,
    listen, release, cancelListen, toggleConversation, say, sayStream, toolResult, repeat, stopSpeaking, setSpeakAnswers, setSettings, resetSettings, level, clock,
  };
}

export type Voice = ReturnType<typeof useVoice>;
