// Batch STT as a stream (voice spec §15.2). OpenAI and ElevenLabs transcribe a whole clip, so this
// buffers the mic audio and decides when a turn ends:
// - push: the turn ends when the user releases the orb.
// - tap: the endpointer ends it after 0.8 s of quiet.
// - conversation: every utterance the endpointer finds is a turn, until cancelled.
// No partial transcripts (batch providers have none); "speech started" still drives barge-in.
import { MIC_RATE, type VoiceMode } from '../../shared/voice';
import { Endpointer, toInt16, wav } from './pcm';
import type { SttHandlers, SttOpts, SttStream, Transcribe } from './types';

const MAX_SECONDS = 60;
const PRE_ROLL_MS = 300;                   // keep a little audio from before speech was detected

export class BatchStt implements SttStream {
  private chunks: Buffer[] = [];
  private bytes = 0;
  private pre: Buffer[] = [];
  private ep: Endpointer;
  private done = false;
  private heard = false;
  private ctl = new AbortController();
  private silence?: NodeJS.Timeout;
  private inflight = 0;

  constructor(private mode: VoiceMode, private o: SttOpts, private h: SttHandlers, private transcribe: Transcribe) {
    this.ep = new Endpointer(MIC_RATE, mode === 'tap' ? 800 : 700,
      () => { this.heard = true; this.h.started(); },
      () => { if (this.mode !== 'push') this.cut(); });
    if (mode !== 'push') this.silence = setTimeout(() => { if (!this.heard) { this.done = true; this.h.nothing(); } }, 8000);
  }

  push(pcm: Buffer) {
    if (this.done) return;
    this.ep.push(toInt16(pcm));
    if (this.mode === 'push' || this.ep.inSpeech) {
      if (this.mode !== 'push' && this.chunks.length === 0) { this.chunks.push(...this.pre); this.bytes += this.pre.reduce((n, b) => n + b.length, 0); }
      this.chunks.push(pcm);
      this.bytes += pcm.length;
      if (this.bytes > MAX_SECONDS * MIC_RATE * 2) this.cut();
    } else {
      this.pre.push(pcm);
      let n = this.pre.reduce((s, b) => s + b.length, 0);
      while (n > (PRE_ROLL_MS / 1000) * MIC_RATE * 2 && this.pre.length > 1) n -= this.pre.shift()!.length;
    }
  }

  /** Push-to-talk released (or tap/conversation endpoint): transcribe what we have. */
  finish() { if (!this.done) this.cut(); }

  cancel() { this.done = true; clearTimeout(this.silence); this.ctl.abort(); }

  private cut() {
    const pcm = Buffer.concat(this.chunks);
    this.chunks = []; this.bytes = 0; this.pre = [];
    if (this.mode !== 'conversation') { this.done = true; clearTimeout(this.silence); }
    if (pcm.length < MIC_RATE * 2 * 0.25) {               // under 250 ms: nothing worth sending
      if (this.mode !== 'conversation') this.h.nothing();
      return;
    }
    this.inflight++;
    this.transcribe(wav(pcm, MIC_RATE), this.o, this.ctl.signal).then(
      text => { const t = text.trim(); if (t) this.h.final(t); else if (this.mode !== 'conversation') this.h.nothing(); },
      err => { if (!this.ctl.signal.aborted) this.h.error((err as Error).message); },
    ).finally(() => { this.inflight--; });
  }
}
