// Browser audio for voice (spec §4): mic capture to PCM16 16 kHz in an AudioWorklet, gapless
// playback of PCM16 24 kHz chunks, levels for the orb, and two short earcons. No dependencies.
import { MIC_RATE, SPEAKER_RATE } from '../../shared/voice';

const CAPTURE_WORKLET = `
class MamaCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / ${MIC_RATE};
    this.buf = new Int16Array(1600); this.n = 0; this.pos = 0; this.acc = 0; this.cnt = 0; this.blocks = 0; this.sum = 0;
    this.port.onmessage = e => {
      if (e.data === 'flush') { if (this.n) this.port.postMessage(this.buf.slice(0, this.n).buffer); this.n = 0; this.port.postMessage('flushed'); }
    };
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      const x = ch[i]; this.sum += x * x; this.acc += x; this.cnt++; this.pos += 1;
      if (this.pos >= this.ratio) {                      // box-filter decimation to 16 kHz
        this.pos -= this.ratio;
        const v = Math.max(-1, Math.min(1, this.acc / this.cnt)); this.acc = 0; this.cnt = 0;
        this.buf[this.n++] = v < 0 ? v * 0x8000 : v * 0x7fff;
        if (this.n === 1600) { const out = this.buf; this.port.postMessage(out.buffer, [out.buffer]); this.buf = new Int16Array(1600); this.n = 0; }
      }
    }
    if (++this.blocks % 6 === 0) { this.port.postMessage({ level: Math.sqrt(this.sum / (ch.length * 6)) }); this.sum = 0; }
    return true;
  }
}
registerProcessor('mama-capture', MamaCapture);
`;

let ctx: AudioContext | null = null;
export function audioContext(): AudioContext {
  if (!ctx) ctx = new AudioContext({ latencyHint: 'interactive' });
  if (ctx.state === 'suspended') void ctx.resume();
  return ctx;
}

/** Microphone → 100 ms PCM16 chunks. Echo cancellation keeps the voice from hearing itself. */
export class Mic {
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;
  private src: MediaStreamAudioSourceNode | null = null;
  private sink: GainNode | null = null;
  level = 0;
  constructor(private onChunk: (pcm: ArrayBuffer) => void) {}

  get open() { return !!this.stream; }

  async start(): Promise<void> {
    if (this.stream) return;
    const ac = audioContext();
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } });
    if (!(ac as any).__mamaCapture) {
      const url = URL.createObjectURL(new Blob([CAPTURE_WORKLET], { type: 'application/javascript' }));
      await ac.audioWorklet.addModule(url);
      URL.revokeObjectURL(url);
      (ac as any).__mamaCapture = true;
    }
    this.src = ac.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(ac, 'mama-capture');
    this.sink = ac.createGain();
    this.sink.gain.value = 0;                              // keeps the graph pulling, silently
    this.node.port.onmessage = e => {
      if (e.data instanceof ArrayBuffer) this.onChunk(e.data);
      else if (e.data && typeof e.data.level === 'number') this.level = e.data.level;
    };
    this.src.connect(this.node).connect(this.sink).connect(ac.destination);
  }

  /** Flush the last partial chunk, then release the mic (the browser's mic indicator turns off). */
  async stop(): Promise<void> {
    const node = this.node;
    if (node) {
      await new Promise<void>(res => {
        const t = setTimeout(res, 150);
        const prev = node.port.onmessage;
        node.port.onmessage = e => { if (e.data === 'flushed') { clearTimeout(t); res(); } else prev?.call(node.port, e); };
        node.port.postMessage('flush');
      });
    }
    this.src?.disconnect(); this.node?.disconnect(); this.sink?.disconnect();
    this.stream?.getTracks().forEach(t => t.stop());
    this.stream = null; this.node = null; this.src = null; this.sink = null; this.level = 0;
  }
}

/** Gapless playback of streamed PCM16 chunks, with a clock for word-timed captions. */
export class Player {
  private next = 0;
  private startAt = 0;
  private sources = new Set<AudioBufferSourceNode>();
  private gain: GainNode | null = null;
  private analyser: AnalyserNode | null = null;
  private data = new Float32Array(512);
  private serverDone = true;
  playing = false;
  onIdle: () => void = () => {};

  private out() {
    const ac = audioContext();
    if (!this.gain) {
      this.gain = ac.createGain();
      this.analyser = ac.createAnalyser();
      this.analyser.fftSize = 512;
      this.gain.connect(this.analyser).connect(ac.destination);
    }
    return { ac, gain: this.gain };
  }

  begin() { this.stop(); this.serverDone = false; }

  push(pcm: ArrayBuffer) {
    const { ac, gain } = this.out();
    const i16 = new Int16Array(pcm, 0, Math.floor(pcm.byteLength / 2));
    if (!i16.length) return;
    const buf = ac.createBuffer(1, i16.length, SPEAKER_RATE);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < i16.length; i++) ch[i] = i16[i] / 32768;
    const src = ac.createBufferSource();
    src.buffer = buf;
    src.connect(gain);
    const at = Math.max(ac.currentTime + 0.05, this.next);
    if (!this.playing) { this.startAt = at; this.playing = true; }
    src.start(at);
    this.next = at + buf.duration;
    this.sources.add(src);
    src.onended = () => { this.sources.delete(src); this.maybeIdle(); };
  }

  /** The server has sent the last chunk. */
  end() { this.serverDone = true; this.maybeIdle(); }

  private maybeIdle() {
    if (this.serverDone && this.sources.size === 0 && this.playing) { this.playing = false; this.next = 0; this.onIdle(); }
    else if (this.serverDone && this.sources.size === 0) this.onIdle();
  }

  /** Stop at once (barge-in, Esc): within one audio frame. */
  stop() {
    for (const s of this.sources) { s.onended = null; try { s.stop(); } catch { /* not started */ } }
    this.sources.clear();
    this.playing = false;
    this.next = 0;
    this.serverDone = true;
  }

  clock(): number { return this.playing ? audioContext().currentTime - this.startAt : -1; }

  level(): number {
    if (!this.analyser || !this.playing) return 0;
    this.analyser.getFloatTimeDomainData(this.data);
    let s = 0;
    for (const x of this.data) s += x * x;
    return Math.sqrt(s / this.data.length);
  }
}

/** Earcons: "listening" rises, "done" falls. 70 ms, quiet, made locally (no network). */
export function earcon(kind: 'open' | 'close' | 'error') {
  try {
    const ac = audioContext();
    const o = ac.createOscillator(), g = ac.createGain();
    const [a, b] = kind === 'open' ? [660, 990] : kind === 'close' ? [880, 590] : [330, 250];
    const t = ac.currentTime;
    o.type = 'sine';
    o.frequency.setValueAtTime(a, t);
    o.frequency.exponentialRampToValueAtTime(b, t + 0.07);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.08, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.09);
    o.connect(g).connect(ac.destination);
    o.start(t);
    o.stop(t + 0.1);
  } catch { /* audio unavailable */ }
}
