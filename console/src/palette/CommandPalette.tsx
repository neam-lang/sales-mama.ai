// ⌘K: one box for everything (spec §5.3) — actions, views, skills, accounts, recent chats.
// Grouped, fuzzy-matched, keyboard driven. Every item only navigates or prefills; nothing runs unseen.
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { fuzzy } from '../chat/Composer';

export interface PaletteItem { id: string; group: string; label: string; hint?: string; keys?: string; icon?: ReactNode; run: () => void }
const GROUPS = ['Actions', 'Go to', 'Skills', 'Accounts', 'Recent chats'];

export function CommandPalette({ open, onClose, items }: { open: boolean; onClose: () => void; items: PaletteItem[] }) {
  const [q, setQ] = useState('');
  const [index, setIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);
  useEffect(() => { if (open) { setQ(''); setIndex(0); requestAnimationFrame(() => input.current?.focus()); } }, [open]);

  const shown = useMemo(() => {
    // Labels may match loosely (skills); hints and long names only on prefix or substring.
    const scored = items.map(it => ({ it, s: Math.max(fuzzy(q, it.label, it.group === 'Skills' || it.group === 'Go to' || it.group === 'Actions'), fuzzy(q, it.hint ?? '', false) / 2) }))
      .filter(x => x.s > 0);
    if (q) scored.sort((a, b) => b.s - a.s);
    const byGroup = GROUPS.map(g => {
      const rows = scored.filter(x => x.it.group === g).slice(0, q ? 6 : g === 'Accounts' ? 4 : 8);
      return { g, best: rows[0]?.s ?? 0, rows: rows.map(x => x.it) };
    }).filter(x => x.rows.length);
    // With a query, the group holding the best match comes first.
    if (q) byGroup.sort((a, b) => b.best - a.best);
    return byGroup;
  }, [items, q]);
  const flat = shown.flatMap(g => g.rows);
  useEffect(() => { setIndex(0); }, [q]);
  useEffect(() => { list.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' }); }, [index]);

  if (!open) return null;
  const run = (it?: PaletteItem) => { if (!it) return; onClose(); it.run(); };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setIndex(i => Math.min(i + 1, flat.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setIndex(i => Math.max(i - 1, 0)); }
    else if (e.key === 'Enter') { e.preventDefault(); run(flat[index]); }
    else if (e.key === 'Escape') { e.preventDefault(); onClose(); }
  };
  let n = -1;
  return (
    <div className="palette-bg" onMouseDown={onClose}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Search or run" onMouseDown={e => e.stopPropagation()} onKeyDown={onKey}>
        <div className="pal-in">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
          <input ref={input} value={q} onChange={e => setQ(e.target.value)} placeholder="Search skills, accounts, chats, or type a command…"
            role="combobox" aria-expanded="true" aria-controls="pal-list" aria-activedescendant={flat[index] ? `pal-${flat[index].id}` : undefined} />
          <kbd>Esc</kbd>
        </div>
        <div className="pal-list" id="pal-list" role="listbox" ref={list}>
          {shown.length === 0 && <p className="pal-empty">Nothing matches “{q}”. Press Enter in the chat to just ask it.</p>}
          {shown.map(({ g, rows }) => (
            <div key={g} className="pal-group" role="group" aria-label={g}>
              <div className="pal-h">{g}</div>
              {rows.map(it => {
                n += 1;
                const i = n;
                return (
                  <div key={it.id} id={`pal-${it.id}`} role="option" aria-selected={i === index} className={`pal-row${i === index ? ' on' : ''}`}
                    onMouseEnter={() => setIndex(i)} onClick={() => run(it)}>
                    <span className="pal-ic">{it.icon}</span>
                    <span className="pal-l">{it.label}</span>
                    {it.hint && <span className="pal-hint">{it.hint}</span>}
                    {it.keys && <kbd>{it.keys}</kbd>}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
        <div className="pal-foot"><span><kbd>↑</kbd><kbd>↓</kbd> move</span><span><kbd>Enter</kbd> open</span><span><kbd>?</kbd> all shortcuts</span></div>
      </div>
    </div>
  );
}

export const SHORTCUTS: [string, string][] = [
  ['⌘K / Ctrl K', 'Search or run anything'],
  ['/', 'Focus the chat and pick a skill'],
  ['@', 'In the composer: mention one of your accounts'],
  ['Enter · Shift Enter', 'Send · new line'],
  ['Esc', 'Stop the run, or close a menu or panel'],
  ['⌘↓ / Ctrl ↓', 'Jump to the latest message'],
  ['g then t · c · k · b · r', 'Go to Today · Chat · Calendar · Book · Reports'],
  ['t · d · w · m · ← →', 'In the calendar: today, day, week, month, previous / next'],
  ['?', 'This sheet'],
];

/** Voice navigation (Sales-Mama-Voice-design-spec.md §16): hold ⌥Space, or go hands-free, and say: */
const VOICE_SAY: [string, string][] = [
  ['Brief me on Kestrel Physio', 'anything you would type'],
  ['Previous answer · next answer', 'move through the chat and hear it'],
  ['Read it · read that again', 'hear the answer in focus, or the last one'],
  ['Open source two · open in canvas', 'open what the answer cites or shows'],
  ['Scroll up · go to the latest', 'move the chat'],
  ['Open the calendar · next week · week view', 'go to a view, move through time'],
  ['Open my last chat · new chat · search', 'switch conversations'],
  ['The second one', 'run suggestion 2'],
  ['Close · stop · mute', 'close a panel, stop speaking, stop reading answers'],
  ['What can I say?', 'hear this list'],
];

export function ShortcutSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  useEffect(() => {
    if (!open) return;
    const esc = (e: globalThis.KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="palette-bg" onMouseDown={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts" onMouseDown={e => e.stopPropagation()}>
        <h2>Keyboard shortcuts</h2>
        <dl>{SHORTCUTS.map(([k, v]) => <div key={k}><dt>{k.split(' · ').map(x => <kbd key={x}>{x}</kbd>)}</dt><dd>{v}</dd></div>)}</dl>
        <h2>Say it</h2>
        <dl className="say">{VOICE_SAY.map(([k, v]) => <div key={k}><dt>“{k}”</dt><dd>{v}</dd></div>)}</dl>
        <button type="button" className="btn" onClick={onClose}>Close</button>
      </div>
    </div>
  );
}
