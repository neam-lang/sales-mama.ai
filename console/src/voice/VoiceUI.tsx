// Voice UI (spec §2, §5, §7): the Mama orb, word-timed captions and the read-back chip.
// Solid concentric rings, never a gradient. State is shown by shape and label, never colour alone.
import { useEffect, useRef, useState, type PointerEvent } from 'react';
import { wordAt, type Word } from '../../shared/voice';
import type { Mention } from '../../shared/mentions';

const PUNCT = /^[.,!?;:…)"'’]+$/;

export type OrbState = 'off' | 'idle' | 'listening' | 'hearing' | 'confirming' | 'thinking' | 'speaking' | 'error';

const LABEL: Record<OrbState, string> = {
  off: 'Voice off', idle: 'Hold to talk', listening: 'Listening', hearing: 'Hearing you', confirming: 'Sending what you said',
  thinking: 'Sales Mama is working', speaking: 'Sales Mama is speaking', error: 'Voice problem',
};

/** Hold = push-to-talk; a quick tap = tap-to-talk (Inworld hears the end); tap while speaking = stop. */
export function Orb({ state, level, onHold, onRelease, onTap, onStop, conversation, disabled }: {
  state: OrbState; level: () => number; onHold: () => void; onRelease: () => void; onTap: () => void; onStop: () => void;
  conversation: boolean; disabled?: boolean;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  const downAt = useRef(0);
  const holding = useRef(false);
  const holdTimer = useRef<ReturnType<typeof setTimeout>>();

  // Rings follow the input or output level, at most 30 times a second (transform only).
  useEffect(() => {
    let raf = 0, lastT = 0, smooth = 0;
    const tick = (t: number) => {
      raf = requestAnimationFrame(tick);
      if (t - lastT < 33) return;
      lastT = t;
      const live = state === 'listening' || state === 'hearing' || state === 'speaking';
      smooth = smooth * 0.6 + (live ? Math.min(1, level()) : 0) * 0.4;
      ref.current?.style.setProperty('--lv', smooth.toFixed(3));
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [state, level]);

  const down = (e: PointerEvent) => {
    if (disabled || e.button !== 0) return;
    if (state === 'speaking') { onStop(); return; }
    downAt.current = performance.now();
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    holdTimer.current = setTimeout(() => { holding.current = true; onHold(); }, 220);
  };
  const up = () => {
    clearTimeout(holdTimer.current);
    if (!downAt.current) return;
    downAt.current = 0;
    if (holding.current) { holding.current = false; onRelease(); return; }
    onTap();
  };

  return (
    <button ref={ref} type="button" className={`orb s-${state}${conversation ? ' convo' : ''}`} disabled={disabled}
      onPointerDown={down} onPointerUp={up} onPointerCancel={up} onContextMenu={e => e.preventDefault()}
      aria-label={`${LABEL[state]}. Hold to talk, or tap to talk. Option Space also works.`} aria-pressed={state === 'listening' || state === 'hearing'}
      title={`${LABEL[state]} · hold to talk · ⌥Space`}>
      <i className="ring r3" aria-hidden="true" /><i className="ring r2" aria-hidden="true" /><i className="ring r1" aria-hidden="true" />
      <i className="arc" aria-hidden="true" />
      <span className="disc" aria-hidden="true">
        {state === 'error'
          ? <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M9 9v2a3 3 0 0 0 5.1 2.1M15 10V5a3 3 0 0 0-5.7-1.3M19 11a7 7 0 0 1-1.2 3.9M5 11a7 7 0 0 0 11.5 5.4M12 18v3M3 3l18 18" /></svg>
          : state === 'speaking'
            ? <svg width="18" height="18" viewBox="0 0 16 16"><rect x="4" y="4" width="8" height="8" rx="2" fill="currentColor" /></svg>
            : <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>}
      </span>
    </button>
  );
}

/** Live words: the partial transcript while listening, or the answer with the spoken word lit. */
export function Captions({ text, words, clock, agent, listening }: { text: string; words: Word[]; clock: () => number; agent?: string; listening?: boolean }) {
  const [at, setAt] = useState(-1);
  useEffect(() => {
    if (listening || !words.length) return;
    let raf = 0;
    const tick = () => { raf = requestAnimationFrame(tick); setAt(wordAt(words, clock())); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [words, clock, listening]);
  if (!text) return null;
  return (
    <div className={`captions${listening ? ' hearing' : ''}${agent ? ` a-${agent}` : ''}`} role="status" aria-live="polite">
      <span className="cap-tag">{listening ? 'You' : 'Sales Mama'}</span>
      {listening || !words.length
        ? <span className="cap-text">{text}</span>
        : <span className="cap-text">{words.map((w, i) => (
            // Punctuation can arrive as its own token, even at the start of a new chunk: no space before it.
            <span key={i} className={i === at ? 'on' : i < at ? 'said' : undefined}>{i > 0 && !PUNCT.test(w.w) ? ' ' : ''}{w.w}</span>
          ))}</span>}
    </div>
  );
}

export interface ReadBackState { id: string; heard: string; prompt: string; unsure: Mention[]; delayMs: number }

/** The read-back chip (spec §2.3): what you said, resolved mentions, and a ring that sends it.
 *  Any key or a tap on Edit pauses it. A mention below 0.9 never auto-sends: pick one first. */
export function ReadBack({ rb, onSend, onEdit, onCancel, onPick }: {
  rb: ReadBackState; onSend: (prompt: string) => void; onEdit: (prompt: string) => void; onCancel: () => void;
  onPick: (m: Mention, id: string | null) => void;
}) {
  const [paused, setPaused] = useState(false);
  const auto = !paused && rb.unsure.length === 0;
  useEffect(() => { setPaused(false); }, [rb.id]);
  useEffect(() => {
    if (!auto) return;
    const t = setTimeout(() => onSend(rb.prompt), rb.delayMs);
    return () => clearTimeout(t);
  }, [auto, rb.id, rb.prompt, rb.delayMs, onSend]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key === 'Enter' && rb.unsure.length === 0) { e.preventDefault(); onSend(rb.prompt); }
      else if (e.key === 'Escape') { e.preventDefault(); onCancel(); }
      else if (!e.metaKey && !e.ctrlKey && e.key.length === 1) { setPaused(true); onEdit(rb.prompt); }
    };
    window.addEventListener('keydown', k, true);
    return () => window.removeEventListener('keydown', k, true);
  }, [rb, onSend, onEdit, onCancel]);

  return (
    <div className="readback" role="group" aria-label="What you said">
      <div className="rb-row">
        <q className="rb-heard">{rb.heard}</q>
        {auto
          ? <span className="rb-ring" style={{ ['--d' as any]: `${rb.delayMs}ms` }} aria-label="Sending"><svg viewBox="0 0 20 20" width="20" height="20"><circle cx="10" cy="10" r="8" /></svg>sending</span>
          : rb.unsure.length ? <span className="rb-wait">Which account?</span> : null}
        <button type="button" className="rb-btn" onClick={() => onSend(rb.prompt)} disabled={rb.unsure.length > 0}>Send now</button>
        <button type="button" className="rb-btn" onClick={() => { setPaused(true); onEdit(rb.prompt); }}>Edit</button>
        <button type="button" className="rb-x" onClick={onCancel} aria-label="Discard what you said">×</button>
      </div>
      {rb.unsure.map(m => (
        <div key={m.start} className="rb-pick">
          <span>“{m.said}”:</span>
          {[{ id: m.id, name: m.name }, ...m.alternatives].map(c => (
            <button key={c.id} type="button" className="rb-chip" onClick={() => onPick(m, c.id)}>@{c.name || c.id}</button>
          ))}
          <button type="button" className="rb-chip plain" onClick={() => onPick(m, null)}>none of these</button>
        </div>
      ))}
      {rb.prompt !== rb.heard && rb.unsure.length === 0 && <p className="rb-prompt">Sends as <code>{rb.prompt}</code></p>}
    </div>
  );
}
