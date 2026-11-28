// Composer v2 (spec §5.2): "/" opens the skill menu, "@" mentions an account, Enter sends,
// Shift+Enter adds a line, Esc stops a run. While a run is going, Enter queues the prompt; it is
// sent when the run ends. Follow-up chips from the last answer sit above it (Perplexity's "related").
import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from 'react';
import type { AccountInfo, SkillInfo } from '../../server/repo';
import { IconArrow } from '../app/Icons';

export interface FollowUp { label: string; prompt: string }

/** Prefix > word-start substring > substring > (optionally) subsequence. 0 = no match. Long free text
 *  (names, descriptions) should pass subsequence=false: scattered letters match almost anything. */
export function fuzzy(query: string, text: string, subsequence = true): number {
  const q = query.toLowerCase(), t = text.toLowerCase();
  if (!q) return 1;
  if (t.startsWith(q)) return 100 - t.length / 100;
  const at = t.indexOf(q);
  if (at >= 0) return 60 - at / 10 + (/[\s/@_-]/.test(t[at - 1] ?? ' ') ? 10 : 0);
  if (!subsequence) return 0;
  let i = 0;
  for (const ch of t) if (ch === q[i]) i++;
  return i === q.length ? 20 - t.length / 100 : 0;
}

type Menu = { kind: '/' | '@'; query: string; start: number } | null;

/** The "/" or "@" token that ends at the caret. Skills only at the very start of the prompt. */
export function tokenAt(text: string, caret: number): Menu {
  const before = text.slice(0, caret);
  const m = /(^|\s)([/@])([\w.-]*)$/.exec(before);
  if (!m) return null;
  const start = before.length - m[2].length - m[3].length;
  if (m[2] === '/' && start !== 0) return null;
  return { kind: m[2] as '/' | '@', query: m[3], start };
}

export function Composer({ manager, skills, accounts, live, canAsk, ask, stop, queued, onQueue, onCancelQueue, followUps, seed, onSeedUsed, compact, inputId, voiceSlot, above }: {
  manager: boolean; skills: SkillInfo[]; accounts: AccountInfo[]; live: boolean; canAsk: boolean;
  ask: (t: string) => void; stop: () => void; queued?: string | null; onQueue?: (t: string) => void; onCancelQueue?: () => void;
  followUps?: FollowUp[]; seed?: string | null; onSeedUsed?: () => void; compact?: boolean; inputId: string;
  /** Voice (spec: Sales-Mama-Voice-design-spec.md): the orb in the row, captions and read-back above it. */
  voiceSlot?: ReactNode; above?: ReactNode;
}) {
  const storeKey = `mama.draft.${inputId}`;
  const [draft, setDraft] = useState(() => { try { return sessionStorage.getItem(storeKey) ?? ''; } catch { return ''; } });
  const [caret, setCaret] = useState(0);
  const [index, setIndex] = useState(0);
  const [dismissed, setDismissed] = useState<number | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { try { sessionStorage.setItem(storeKey, draft); } catch { /* private mode */ } }, [draft, storeKey]);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 8 * 24 + 20)}px`;
  }, [draft]);
  useEffect(() => {
    if (seed == null) return;
    setDraft(seed);
    setDismissed(null);
    onSeedUsed?.();
    requestAnimationFrame(() => { const el = ref.current; if (!el) return; el.focus(); el.setSelectionRange(seed.length, seed.length); setCaret(seed.length); });
  }, [seed, onSeedUsed]);

  const menu = useMemo(() => { const m = tokenAt(draft, caret); return m && m.start !== dismissed ? m : null; }, [draft, caret, dismissed]);
  const options = useMemo(() => {
    if (!menu) return [];
    if (menu.kind === '/') {
      return skills.filter(s => manager || s.role !== 'manager')
        .map(s => ({ s, score: Math.max(fuzzy(menu.query, s.name), fuzzy(menu.query, s.name.replace(/^mama-/, '')), fuzzy(menu.query, s.description, false) / 3) }))
        .filter(x => x.score > 0).sort((a, b) => b.score - a.score).slice(0, 8)
        .map(({ s }) => ({ key: s.name, insert: `/${s.name} `, title: `/${s.name}`, sub: s.description, badge: s.role === 'manager' ? 'manager' : '' }));
    }
    return accounts.map(a => ({ a, score: Math.max(fuzzy(menu.query, a.name, false), fuzzy(menu.query, a.id, false)) }))
      .filter(x => x.score > 0).sort((x, y) => y.score - x.score).slice(0, 8)
      .map(({ a }) => ({ key: a.id, insert: `@${a.id} `, title: a.name || a.id, sub: `${a.id} · ${a.stage || 'new'}${a.owner && manager ? ` · ${a.owner}` : ''}`, badge: a.tier, market: a.market }));
  }, [menu, skills, accounts, manager]);
  useEffect(() => { setIndex(0); }, [menu?.kind, menu?.query]);

  const choose = (i: number) => {
    const o = options[i];
    if (!o || !menu) return;
    const next = draft.slice(0, menu.start) + o.insert + draft.slice(caret);
    const pos = menu.start + o.insert.length;
    setDraft(next);
    requestAnimationFrame(() => { ref.current?.focus(); ref.current?.setSelectionRange(pos, pos); setCaret(pos); });
  };

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    const text = draft.trim();
    if (!text) return;
    if (live && onQueue) { onQueue(text); setDraft(''); return; }
    if (!canAsk) return;
    ask(text);
    setDraft('');
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (menu && options.length) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setIndex(i => (i + 1) % options.length); return; }
      if (e.key === 'ArrowUp') { e.preventDefault(); setIndex(i => (i - 1 + options.length) % options.length); return; }
      if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); choose(index); return; }
      if (e.key === 'Escape') { e.preventDefault(); setDismissed(menu.start); return; }
    }
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); return; }
    if (e.key === 'Escape' && live) stop();
  };
  const track = () => setCaret(ref.current?.selectionStart ?? draft.length);
  const placeholder = live ? 'Type your next request; it is sent when this run finishes'
    : manager ? 'Ask, approve in a sentence, / for skills, @ for accounts' : 'Ask anything, / for skills, @ for accounts';

  return (
    <div className={`dock${compact ? ' compact' : ''}`}>
      {above}
      {!compact && (followUps?.length || queued) ? (
        <div className="followups" aria-label="Suggested next steps">
          {queued && (
            <span className="queued"><b>Queued</b>{queued.length > 60 ? `${queued.slice(0, 57)}…` : queued}
              <button type="button" onClick={onCancelQueue} aria-label="Cancel the queued prompt">×</button></span>
          )}
          {!live && followUps?.map((f, i) => (
            <button key={f.prompt} type="button" className="fu" style={{ animationDelay: `${i * 50}ms` }} disabled={!canAsk} onClick={() => ask(f.prompt)} title={f.prompt}>
              {f.label}<IconArrow size={14} />
            </button>
          ))}
        </div>
      ) : null}
      <div className="cw">
      {menu && options.length > 0 && (
        <ul className="menu" role="listbox" aria-label={menu.kind === '/' ? 'Skills' : 'Accounts'}>
          <li className="menu-h" aria-hidden="true">{menu.kind === '/' ? 'Skills' : 'Your accounts'}<span>↑↓ to move · Enter to pick · Esc to close</span></li>
          {options.map((o, i) => (
            <li key={o.key} role="option" aria-selected={i === index} className={i === index ? 'on' : undefined}
              onMouseDown={e => { e.preventDefault(); choose(i); }} onMouseEnter={() => setIndex(i)}>
              <span className="m-title">{o.title}</span>
              {(o as { market?: string }).market ? <b className="mk" style={{ ['--m' as any]: `var(--m-${(o as { market?: string }).market})` }}>{(o as { market?: string }).market}</b> : null}
              {o.badge ? <span className={`m-badge${menu.kind === '@' ? ` tier t-${o.badge}` : ''}`}>{o.badge}</span> : null}
              <span className="m-sub">{o.sub}</span>
            </li>
          ))}
        </ul>
      )}
      <form className={`composer${live ? ' busy' : ''}`} onSubmit={submit}>
        <div className="compose-row">
          <label htmlFor={inputId} className="sr">Ask Sales Mama</label>
          <textarea id={inputId} ref={ref} rows={1} value={draft} placeholder={placeholder}
            onChange={e => { setDraft(e.target.value); setCaret(e.target.selectionStart ?? e.target.value.length); setDismissed(null); }}
            onKeyDown={onKey} onKeyUp={track} onClick={track} onBlur={() => window.setTimeout(() => setDismissed(menu?.start ?? null), 120)}
            aria-autocomplete="list" aria-expanded={!!menu && options.length > 0} />
          {voiceSlot}
          {live && !draft.trim()
            ? <button type="button" className="go stop" aria-label="Stop the run (Esc)" onClick={stop}>
                <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16"><rect x="3" y="3" width="10" height="10" rx="2" fill="currentColor" /></svg>
              </button>
            : <button type="submit" className="go" aria-label={live ? 'Queue this prompt' : 'Ask Sales Mama'} disabled={!draft.trim() || (!live && !canAsk)}><IconArrow size={20} /></button>}
        </div>
      </form>
      </div>
      {!compact && <p className="dock-hint"><kbd>/</kbd> skills · <kbd>@</kbd> accounts · <kbd>Enter</kbd> send · <kbd>Shift</kbd>+<kbd>Enter</kbd> new line · <kbd>⌘K</kbd> search{voiceSlot ? <> · hold <kbd>⌥</kbd>+<kbd>Space</kbd> talk</> : null}{live ? <> · <kbd>Esc</kbd> stop</> : null}</p>}
    </div>
  );
}
