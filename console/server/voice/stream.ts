// Streaming speech for providers without a native text stream (OpenAI, ElevenLabs): sentences are
// spoken in order, one request each, and word timings are offset by the audio already sent.
import type { SpeakHandlers, SpeakOpts, SpeechStream, TtsEngine } from './types';

export function sentenceQueue(tts: TtsEngine, id: string, o: SpeakOpts, h: SpeakHandlers): SpeechStream & { cancel(): void } {
  const queue: string[] = [];
  let busy = false, ended = false, done = false, seconds = 0, n = 0, current = '';
  const next = () => {
    if (done || busy) return;
    const text = queue.shift();
    if (text === undefined) { if (ended) { done = true; h.end(true); } return; }
    busy = true;
    current = `${id}-${n++}`;
    let sent = 0;
    void tts.speak(current, text, o, {
      audio: b => { sent += b.length; h.audio(b); },
      words: w => h.words(w.map(x => ({ ...x, start: x.start + seconds, end: x.end + seconds }))),
      end: (ok, err) => {
        seconds += sent / 2 / 24000;
        busy = false;
        if (!ok && err) { done = true; h.end(false, err); return; }
        next();
      },
    });
  };
  return {
    push: t => { if (t.trim()) { queue.push(t); next(); } },
    end: () => { ended = true; next(); },
    cancel: () => { done = true; queue.length = 0; if (busy) tts.cancel(current); },
  };
}
