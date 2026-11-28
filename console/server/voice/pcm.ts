// PCM helpers shared by the providers (pure, tested): resampling, WAV wrapping, keeping chunks
// sample-aligned, a simple endpointer for batch STT, and a streaming JSON-object splitter.

/** Streaming linear resampler for PCM16 mono (e.g. 16 kHz mic → 24 kHz for OpenAI Realtime). */
export class Resampler {
  private t = 0;
  private prev = 0;
  constructor(private from: number, private to: number) {}
  push(inp: Int16Array): Int16Array {
    if (this.from === this.to) return inp;
    const step = this.from / this.to;
    const out: number[] = [];
    // Position t is relative to inp[0]; index -1 is the last sample of the previous chunk.
    while (this.t <= inp.length - 1) {
      const i = Math.floor(this.t), f = this.t - i;
      const a = i < 0 ? this.prev : inp[i];
      const b = i + 1 < inp.length ? inp[i + 1] : a;
      out.push(Math.round(a + (b - a) * f));
      this.t += step;
    }
    this.t -= inp.length;
    if (inp.length) this.prev = inp[inp.length - 1];
    return Int16Array.from(out);
  }
}

export const toInt16 = (b: Buffer) => new Int16Array(b.buffer.slice(b.byteOffset, b.byteOffset + (b.length & ~1)));
export const fromInt16 = (a: Int16Array) => Buffer.from(a.buffer, a.byteOffset, a.byteLength);

/** Wrap raw PCM16 mono in a WAV header (for batch STT uploads). */
export function wav(pcm: Buffer, rate: number): Buffer {
  const h = Buffer.alloc(44);
  h.write('RIFF', 0); h.writeUInt32LE(36 + pcm.length, 4); h.write('WAVE', 8);
  h.write('fmt ', 12); h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22);
  h.writeUInt32LE(rate, 24); h.writeUInt32LE(rate * 2, 28); h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34);
  h.write('data', 36); h.writeUInt32LE(pcm.length, 40);
  return Buffer.concat([h, pcm]);
}

/** HTTP chunks can split a sample in two; this keeps every chunk an even number of bytes. */
export class PcmAligner {
  private carry: Buffer | null = null;
  push(b: Buffer): Buffer {
    const all = this.carry ? Buffer.concat([this.carry, b]) : b;
    const even = all.length & ~1;
    this.carry = even < all.length ? all.subarray(even) : null;
    return all.subarray(0, even);
  }
}

/**
 * Endpointing for batch STT providers (OpenAI, ElevenLabs), which have no turn detection of their own.
 * Energy-based on 20 ms frames with an adaptive noise floor: speech starts after 3 loud frames and
 * ends after `silenceMs` of quiet. The browser's noise suppression keeps the floor low.
 */
export class Endpointer {
  private noise = 0.004;
  private loud = 0;
  private quietMs = 0;
  private carry: number[] = [];
  inSpeech = false;
  constructor(private rate: number, private silenceMs = 800, private onStart: () => void = () => {}, private onEnd: () => void = () => {}) {}

  push(samples: Int16Array) {
    const frame = Math.round(this.rate * 0.02);
    const all = this.carry.length ? Int16Array.from([...this.carry, ...samples]) : samples;
    let i = 0;
    for (; i + frame <= all.length; i += frame) {
      let s = 0;
      for (let j = i; j < i + frame; j++) { const x = all[j] / 32768; s += x * x; }
      this.frame(Math.sqrt(s / frame));
    }
    this.carry = Array.from(all.subarray(i));
  }

  private frame(rms: number) {
    const threshold = Math.max(0.015, this.noise * 3.5);
    if (!this.inSpeech) {
      this.noise = this.noise * 0.95 + Math.min(rms, 0.05) * 0.05;
      this.loud = rms > threshold ? this.loud + 1 : 0;
      if (this.loud >= 3) { this.inSpeech = true; this.quietMs = 0; this.onStart(); }
      return;
    }
    this.quietMs = rms > threshold * 0.7 ? 0 : this.quietMs + 20;
    if (this.quietMs >= this.silenceMs) { this.inSpeech = false; this.loud = 0; this.onEnd(); }
  }
}

/** Split a stream of concatenated or newline-separated JSON objects. Returns objects and the remainder. */
export function jsonObjects(buf: string): { objects: any[]; rest: string } {
  const objects: any[] = [];
  let depth = 0, inStr = false, esc = false, start = -1;
  for (let i = 0; i < buf.length; i++) {
    const c = buf[i];
    if (inStr) { if (esc) esc = false; else if (c === '\\') esc = true; else if (c === '"') inStr = false; continue; }
    if (c === '"') { inStr = true; continue; }
    if (c === '{') { if (depth === 0) start = i; depth++; }
    else if (c === '}' && depth > 0) {
      depth--;
      if (depth === 0 && start >= 0) {
        try { objects.push(JSON.parse(buf.slice(start, i + 1))); } catch { /* skip a broken object */ }
        start = -1;
      }
    }
  }
  return { objects, rest: depth > 0 && start >= 0 ? buf.slice(start) : '' };
}

/** Character alignment (ElevenLabs) → word timings. */
export function charsToWords(chars: string[], starts: number[], ends: number[], offset = 0): { w: string; start: number; end: number }[] {
  const words: { w: string; start: number; end: number }[] = [];
  let cur = '', s = 0, e = 0;
  chars.forEach((ch, i) => {
    if (/\s/.test(ch)) { if (cur) words.push({ w: cur, start: s + offset, end: e + offset }); cur = ''; return; }
    if (!cur) s = starts[i] ?? 0;
    cur += ch;
    e = ends[i] ?? s;
  });
  if (cur) words.push({ w: cur, start: s + offset, end: e + offset });
  return words;
}
