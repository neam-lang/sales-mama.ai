// OpenAI voice (voice spec §15): TTS (/v1/audio/speech, PCM 24 kHz), batch STT
// (/v1/audio/transcriptions) and Realtime ("GPT live", wss /v1/realtime).
// In Realtime, GPT is the conversational voice but NOT the brain: it must call ask_sales_mama for
// anything about the user's work, and in strict mode it may only call tools and then say the
// tool's answer. MAMA_OPENAI_HTTP / MAMA_OPENAI_WS point at a mock in tests.
import WebSocket from 'ws';
import { APPROVAL_REPLY, MIC_RATE, SPEAKER_RATE, TOOL_COMMANDS, type VoiceSettings } from '../../shared/voice';
import { fromInt16, PcmAligner, Resampler, toInt16 } from './pcm';
import type { SpeakHandlers, SpeakOpts, SttOpts, TtsEngine } from './types';

const HTTP = () => process.env.MAMA_OPENAI_HTTP ?? 'https://api.openai.com';
const WSS = () => process.env.MAMA_OPENAI_WS ?? 'wss://api.openai.com';
export const OPENAI_MODELS = {
  tts: process.env.MAMA_OPENAI_TTS_MODEL ?? 'gpt-4o-mini-tts',
  stt: process.env.MAMA_OPENAI_STT_MODEL ?? 'gpt-4o-mini-transcribe',
  realtime: process.env.MAMA_OPENAI_REALTIME_MODEL ?? 'gpt-realtime',
};

async function explain(r: Response): Promise<string> {
  let detail = '';
  try { detail = (await r.json() as { error?: { message?: string } }).error?.message ?? ''; } catch { /* not json */ }
  if (r.status === 401) return 'OpenAI refused the API key. Check ~/.config/sales-mama/openai.json.';
  if (r.status === 429) return 'OpenAI rate limit or quota reached. Try again in a moment.';
  return `OpenAI error ${r.status}${detail ? `: ${detail}` : ''}`;
}

export class OpenAiTts implements TtsEngine {
  private ctl = new Map<string, AbortController>();
  constructor(private key: string) {}

  async speak(id: string, text: string, o: SpeakOpts, h: SpeakHandlers) {
    const ctl = new AbortController();
    this.ctl.set(id, ctl);
    try {
      const r = await fetch(`${HTTP()}/v1/audio/speech`, {
        method: 'POST', signal: ctl.signal,
        headers: { Authorization: `Bearer ${this.key}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: OPENAI_MODELS.tts, voice: o.voiceId, input: text, response_format: 'pcm',
          // gpt-4o-mini-tts takes delivery instructions instead of a speed number.
          instructions: `Warm, clear and brisk, like a helpful colleague.${o.style ? ` ${o.style[0].toUpperCase()}${o.style.slice(1)}.` : ''}${o.rate > 1.05 ? ' Speak a little faster than usual.' : o.rate < 0.95 ? ' Speak a little slower than usual.' : ''}`,
        }),
      });
      if (!r.ok || !r.body) { this.done(id, h, false, await explain(r)); return; }
      const align = new PcmAligner();
      for await (const chunk of r.body as unknown as AsyncIterable<Uint8Array>) {
        if (!this.ctl.has(id)) return;
        const b = align.push(Buffer.from(chunk));
        if (b.length) h.audio(b);
      }
      this.done(id, h, true);
    } catch (e) {
      if (ctl.signal.aborted) return;
      this.done(id, h, false, (e as Error).message);
    }
  }

  private done(id: string, h: SpeakHandlers, ok: boolean, err?: string) {
    if (!this.ctl.delete(id)) return;
    h.end(ok, err);
  }

  cancel(id: string) { const c = this.ctl.get(id); this.ctl.delete(id); c?.abort(); }
  close() { for (const c of this.ctl.values()) c.abort(); this.ctl.clear(); }
}

export function openAiTranscribe(key: string) {
  return async (wavData: Buffer, o: SttOpts, signal: AbortSignal): Promise<string> => {
    const form = new FormData();
    form.append('file', new Blob([wavData], { type: 'audio/wav' }), 'speech.wav');
    form.append('model', OPENAI_MODELS.stt);
    form.append('response_format', 'json');
    if (o.lang && o.lang !== 'auto') form.append('language', o.lang.slice(0, 2));
    if (o.prompts?.length) form.append('prompt', `Sales Mama. Account names: ${o.prompts.slice(0, 60).join(', ')}.`);
    const r = await fetch(`${HTTP()}/v1/audio/transcriptions`, { method: 'POST', signal, headers: { Authorization: `Bearer ${key}` }, body: form });
    if (!r.ok) throw new Error(await explain(r));
    return String((await r.json() as { text?: string }).text ?? '');
  };
}

// ---------------------------------------------------------------------------------------------
// Realtime ("GPT live")
// ---------------------------------------------------------------------------------------------
export function realtimeInstructions(strict: boolean): string {
  return [
    'You are the voice of Sales Mama, an assistant for a small B2B sales team in Singapore, Malaysia and India.',
    'You are only the voice. You do not know the user\'s accounts, contacts, meetings, numbers, products or company.',
    'For any request about their work, call ask_sales_mama with the request in the user\'s own words. Keep account names exactly as said. Never answer such a request yourself.',
    'To move around the console, call voice_command: stop, new chat, repeat, help, mute or unmute; open a view (today, chat, calendar, book, reports); previous, next, first or last answer; read the answer; scroll up, down, top or bottom; open source n; open in canvas; close; open the last chat; search; next or previous week; day, week or month view; or pick suggestion n ("the second one").',
    'When ask_sales_mama returns, say its "say" text to the user word for word. Do not add, change or round any name, number, time or product.',
    `You can never send, approve or assign anything, and you never claim that something was sent. If asked to, say: "${APPROVAL_REPLY}"`,
    strict
      ? 'Do not make small talk or answer from your own knowledge: every user turn is either ask_sales_mama or voice_command.'
      : 'You may greet the user and ask one short clarifying question, but anything about their work goes to ask_sales_mama.',
    'Keep replies under 40 words. Speak English with a warm, brisk tone.',
  ].join('\n');
}

export const REALTIME_TOOLS = [
  {
    type: 'function', name: 'ask_sales_mama',
    description: 'Ask Sales Mama (the team\'s grounded sales assistant) anything about the user\'s day, accounts, contacts, meetings, drafts, replies, leads, companies or reports. Returns the answer to speak.',
    parameters: { type: 'object', properties: { request: { type: 'string', description: 'The user\'s request in their own words, with account names as said.' } }, required: ['request'] },
  },
  {
    type: 'function', name: 'voice_command',
    description: 'Navigate and control the Sales Mama console by voice: move through answers and read them, open sources or the canvas, scroll, switch views, move the calendar, reopen chats, search, stop, mute, or pick a suggested next step.',
    parameters: { type: 'object', properties: { command: { type: 'string', enum: TOOL_COMMANDS } }, required: ['command'] },
  },
];

export interface RealtimeHandlers {
  started(): void;
  heard(text: string): void;
  speechBegin(id: string): void;
  audio(pcm24k: Buffer): void;
  speechText(id: string, text: string): void;
  speechEnd(id: string, interrupted: boolean): void;
  spoken(id: string, transcript: string): void;
  toolPrompt(callId: string, prompt: string): void;
  toolCommand(callId: string, command: string): void;
  error(msg: string): void;
  closed(): void;
}

/** One live conversation with gpt-realtime. Mic audio in at 16 kHz is resampled to 24 kHz. */
export class Realtime {
  private ws: WebSocket;
  private open = false;
  private queue: string[] = [];
  private up = new Resampler(MIC_RATE, SPEAKER_RATE);
  private current: { id: string; text: string } | null = null;
  private interrupted = new Set<string>();
  private relayCalls = new Map<string, string>();       // call_id → the answer GPT must say
  constructor(key: string, private s: VoiceSettings, private h: RealtimeHandlers) {
    this.ws = new WebSocket(`${WSS()}/v1/realtime?model=${encodeURIComponent(OPENAI_MODELS.realtime)}`, { headers: { Authorization: `Bearer ${key}` } });
    this.ws.on('open', () => {
      this.open = true;
      this.send({
        type: 'session.update',
        session: {
          type: 'realtime',
          model: OPENAI_MODELS.realtime,
          instructions: realtimeInstructions(s.strict),
          output_modalities: ['audio'],
          audio: {
            input: {
              format: { type: 'audio/pcm', rate: SPEAKER_RATE },
              noise_reduction: { type: 'near_field' },
              transcription: { model: OPENAI_MODELS.stt, ...(s.lang !== 'auto' ? { language: s.lang.slice(0, 2) } : {}) },
              turn_detection: { type: 'semantic_vad', eagerness: 'auto', create_response: true, interrupt_response: true },
            },
            output: { format: { type: 'audio/pcm', rate: SPEAKER_RATE }, voice: s.voices.realtime, speed: s.rate },
          },
          tools: REALTIME_TOOLS,
          tool_choice: s.strict ? 'required' : 'auto',
        },
      });
      for (const m of this.queue) this.ws.send(m);
      this.queue = [];
    });
    this.ws.on('unexpected-response', (_q, res) => { this.h.error(res.statusCode === 401 ? 'OpenAI refused the API key. Check ~/.config/sales-mama/openai.json.' : `OpenAI Realtime HTTP ${res.statusCode}`); this.h.closed(); });
    this.ws.on('error', e => this.h.error(e.message));
    this.ws.on('close', () => { if (this.current) this.h.speechEnd(this.current.id, true); this.current = null; this.h.closed(); });
    this.ws.on('message', d => this.onEvent(String(d)));
  }

  private send(o: object) {
    const s = JSON.stringify(o);
    if (this.open && this.ws.readyState === WebSocket.OPEN) this.ws.send(s); else this.queue.push(s);
  }

  push(pcm16k: Buffer) {
    const up = this.up.push(toInt16(pcm16k));
    if (up.length) this.send({ type: 'input_audio_buffer.append', audio: fromInt16(up).toString('base64') });
  }

  /** Sales Mama answered: hand it to GPT and make it say exactly that. */
  toolResult(callId: string, text: string) {
    this.relayCalls.set(callId, text);
    this.send({ type: 'conversation.item.create', item: { type: 'function_call_output', call_id: callId, output: JSON.stringify({ say: text }) } });
    this.send({ type: 'response.create', response: { tool_choice: 'none', instructions: `Say this to the user, word for word, and nothing else: ${JSON.stringify(text)}` } });
  }

  /** A voice command ran: acknowledge without speaking. */
  commandDone(callId: string) {
    this.send({ type: 'conversation.item.create', item: { type: 'function_call_output', call_id: callId, output: JSON.stringify({ ok: true }) } });
  }

  /** Barge-in or Esc: stop the current answer. */
  stopSpeaking() {
    if (!this.current) return;
    this.interrupted.add(this.current.id);
    this.send({ type: 'response.cancel' });
    this.h.speechEnd(this.current.id, true);
    this.current = null;
  }

  close() { this.ws.close(); }

  /** The text GPT was told to say for the response now speaking (for the grounding check). */
  sourceFor(): string | undefined { return [...this.relayCalls.values()].pop(); }

  private onEvent(raw: string) {
    let e: any;
    try { e = JSON.parse(raw); } catch { return; }
    switch (e.type) {
      case 'input_audio_buffer.speech_started':
        this.h.started();
        if (this.current) { this.interrupted.add(this.current.id); this.h.speechEnd(this.current.id, true); this.current = null; }
        break;
      case 'conversation.item.input_audio_transcription.completed':
        if (e.transcript) this.h.heard(String(e.transcript).trim());
        break;
      case 'response.output_audio.delta':
      case 'response.audio.delta': {                     // GA and beta event names
        const id = String(e.response_id ?? 'r');
        if (this.interrupted.has(id)) return;
        if (!this.current || this.current.id !== id) { this.current = { id, text: '' }; this.h.speechBegin(id); }
        this.h.audio(Buffer.from(String(e.delta ?? ''), 'base64'));
        break;
      }
      case 'response.output_audio_transcript.delta':
      case 'response.audio_transcript.delta':
        if (this.current && this.current.id === String(e.response_id ?? 'r')) { this.current.text += String(e.delta ?? ''); this.h.speechText(this.current.id, this.current.text); }
        break;
      case 'response.output_audio_transcript.done':
      case 'response.audio_transcript.done':
        if (e.transcript) this.h.spoken(String(e.response_id ?? 'r'), String(e.transcript));
        break;
      case 'response.output_item.done': {
        const item = e.item;
        if (item?.type !== 'function_call') break;
        let args: any = {};
        try { args = JSON.parse(item.arguments || '{}'); } catch { /* bad arguments */ }
        if (item.name === 'ask_sales_mama' && typeof args.request === 'string' && args.request.trim()) this.h.toolPrompt(item.call_id, args.request.trim().slice(0, 2000));
        else if (item.name === 'voice_command' && typeof args.command === 'string') this.h.toolCommand(item.call_id, args.command);
        else this.send({ type: 'conversation.item.create', item: { type: 'function_call_output', call_id: item.call_id, output: JSON.stringify({ error: 'unknown tool' }) } });
        break;
      }
      case 'response.done': {
        const id = String(e.response?.id ?? 'r');
        if (this.current && this.current.id === id) { this.h.speechEnd(id, false); this.current = null; }
        this.interrupted.delete(id);
        break;
      }
      case 'error':
        if (e.error?.code === 'response_cancel_not_active') break;
        this.h.error(`OpenAI Realtime: ${e.error?.message ?? 'error'}`);
        break;
    }
  }
}
