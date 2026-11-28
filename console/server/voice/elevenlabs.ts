// ElevenLabs voice (voice spec §15): streaming TTS with character timestamps (PCM 24 kHz) and
// batch STT (Scribe). MAMA_ELEVENLABS_HTTP points at a mock in tests.
import type { VoiceOption } from '../../shared/voice';
import { charsToWords, jsonObjects, PcmAligner } from './pcm';
import type { SpeakHandlers, SpeakOpts, SttOpts, TtsEngine } from './types';

const HTTP = () => process.env.MAMA_ELEVENLABS_HTTP ?? 'https://api.elevenlabs.io';
export const ELEVEN_MODELS = {
  tts: process.env.MAMA_ELEVENLABS_TTS_MODEL ?? 'eleven_flash_v2_5',
  stt: process.env.MAMA_ELEVENLABS_STT_MODEL ?? 'scribe_v1',
};

async function explain(r: Response): Promise<string> {
  let detail = '';
  try { const j = await r.json() as { detail?: { message?: string } | string }; detail = typeof j.detail === 'string' ? j.detail : j.detail?.message ?? ''; } catch { /* not json */ }
  if (r.status === 401) return 'ElevenLabs refused the API key. Check ~/.config/sales-mama/elevenlabs.json.';
  if (r.status === 429) return 'ElevenLabs rate limit or quota reached. Try again in a moment.';
  return `ElevenLabs error ${r.status}${detail ? `: ${detail}` : ''}`;
}

export class ElevenTts implements TtsEngine {
  private ctl = new Map<string, AbortController>();
  constructor(private key: string) {}

  async speak(id: string, text: string, o: SpeakOpts, h: SpeakHandlers) {
    const ctl = new AbortController();
    this.ctl.set(id, ctl);
    try {
      const r = await fetch(`${HTTP()}/v1/text-to-speech/${encodeURIComponent(o.voiceId)}/stream/with-timestamps?output_format=pcm_24000`, {
        method: 'POST', signal: ctl.signal,
        headers: { 'xi-api-key': this.key, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text, model_id: ELEVEN_MODELS.tts,
          ...(o.lang && o.lang !== 'auto' ? { language_code: o.lang.slice(0, 2) } : {}),
          voice_settings: { stability: 0.5, similarity_boost: 0.75, speed: Math.min(1.2, Math.max(0.7, o.rate)) },
        }),
      });
      if (!r.ok || !r.body) { this.done(id, h, false, await explain(r)); return; }
      const align = new PcmAligner();
      let buf = '', seconds = 0, lastEnd = 0;
      const dec = new TextDecoder();
      for await (const chunk of r.body as unknown as AsyncIterable<Uint8Array>) {
        if (!this.ctl.has(id)) return;
        buf += dec.decode(chunk, { stream: true });
        const { objects, rest } = jsonObjects(buf);
        buf = rest;
        for (const obj of objects) {
          const audio = obj.audio_base64 ? align.push(Buffer.from(obj.audio_base64, 'base64')) : Buffer.alloc(0);
          const a = obj.alignment ?? obj.normalized_alignment;
          if (a?.characters?.length) {
            // Times are cumulative in practice; if a chunk restarts near zero, offset it by the audio so far.
            const first = a.character_start_times_seconds?.[0] ?? 0;
            const offset = first + 0.05 < lastEnd ? seconds : 0;
            const words = charsToWords(a.characters, a.character_start_times_seconds ?? [], a.character_end_times_seconds ?? [], offset);
            if (words.length) { h.words(words); lastEnd = words[words.length - 1].end; }
          }
          if (audio.length) { seconds += audio.length / 2 / 24000; h.audio(audio); }
        }
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

export function elevenTranscribe(key: string) {
  return async (wavData: Buffer, o: SttOpts, signal: AbortSignal): Promise<string> => {
    const form = new FormData();
    form.append('model_id', ELEVEN_MODELS.stt);
    form.append('file', new Blob([wavData], { type: 'audio/wav' }), 'speech.wav');
    if (o.lang && o.lang !== 'auto') form.append('language_code', o.lang.slice(0, 2));
    form.append('tag_audio_events', 'false');
    const r = await fetch(`${HTTP()}/v1/speech-to-text`, { method: 'POST', signal, headers: { 'xi-api-key': key }, body: form });
    if (!r.ok) throw new Error(await explain(r));
    return String((await r.json() as { text?: string }).text ?? '');
  };
}

export async function listElevenVoices(key: string): Promise<VoiceOption[]> {
  const r = await fetch(`${HTTP()}/v1/voices`, { headers: { 'xi-api-key': key } });
  if (!r.ok) throw new Error(await explain(r));
  const d = await r.json() as { voices?: { voice_id: string; name: string; labels?: Record<string, string> }[] };
  return (d.voices ?? []).map(v => ({
    id: v.voice_id, name: v.name,
    gender: v.labels?.gender === 'male' || v.labels?.gender === 'female' ? v.labels.gender : '',
    note: [v.labels?.accent, v.labels?.description ?? v.labels?.descriptive].filter(Boolean).join(', '),
  }));
}
