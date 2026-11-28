// The ink header: brand, live market clocks with send-window state, run status, theme, new chat.
// Underneath, the pulse bar: one gliding dot per running agent, visible from every screen (spec §2).
import type { ReactNode } from 'react';
import type { Rail } from '../../shared/protocol';
import { sendWindow } from '../../shared/window';
import { clock, useNow } from '../hooks/useNow';
import type { Theme } from '../hooks/useTheme';
import { IconAuto, IconMoon, IconPlus, IconSun } from './Icons';

export interface PulseLane { id: string; agent: string; running: boolean }

function shortWindow(label: string, open: boolean): string {
  if (open) return label.replace(/^Send window open · closes in /, 'open · ') + ' left';
  return label.replace(/^Send window opens in /, 'opens in ').replace(/^Next send window /, 'next ').replace(/^No send window.*/, 'no window soon');
}

export function MarketClocks({ rail }: { rail: Rail | null }) {
  const now = useNow(30_000);
  const markets = Object.entries(rail?.markets ?? {});
  if (!markets.length) return null;
  return (
    <div className="clocks" aria-label="Market clocks">
      {markets.map(([code, cfg]) => {
        const w = sendWindow(code, cfg, now);
        return (
          <span key={code} className={`clock${w.open ? ' open' : ''}`} style={{ ['--m' as any]: `var(--m-${code}, var(--mama))` }} title={`${w.label} · ${w.detail}`}>
            <b className="mk">{code}</b>
            <time>{clock(now, cfg.tz)}</time>
            <i className="lamp" aria-hidden="true" />
            <span className="win">{shortWindow(w.label, w.open)}</span>
          </span>
        );
      })}
    </div>
  );
}

export function Header({ rail, status, live, theme, onTheme, onNewChat, newChatDisabled, lanes, onSearch, nextUp, extra }: {
  rail: Rail | null; status: string; live: boolean; theme: Theme; onTheme: () => void;
  onNewChat: () => void; newChatDisabled: boolean; lanes: PulseLane[]; onSearch: () => void; nextUp?: ReactNode; extra?: ReactNode;
}) {
  const me = rail?.me;
  const initials = (me?.name || me?.id || '?').split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase();
  const ThemeIcon = theme === 'dark' ? IconMoon : theme === 'light' ? IconSun : IconAuto;
  return (
    <>
      <header className="hdr">
        <div className="brand"><span className="logo" aria-hidden="true">SM</span><span className="word">Sales Mama</span></div>
        <MarketClocks rail={rail} />
        <button type="button" className="hdr-search" onClick={onSearch} aria-label="Search or run (Command K)">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
          <span>Search or run…</span><kbd>⌘K</kbd>
        </button>
        {nextUp}
        <div className="hdr-right">
          <span className={`run-status${live ? ' is-live' : ''}`} role="status"><i aria-hidden="true" />{status}</span>
          {extra}
          <button type="button" className="icon-btn" onClick={onTheme} aria-label={`Theme: ${theme}. Switch theme`} title={`Theme: ${theme}`}><ThemeIcon size={18} /></button>
          <button type="button" className="hdr-btn" onClick={onNewChat} disabled={newChatDisabled}><IconPlus size={16} /><span>New chat</span></button>
          {me && <span className="avatar" title={`${me.name} · ${me.role}`} aria-label={`${me.name}, ${me.role}`}>{initials}</span>}
        </div>
      </header>
      <PulseBar live={live} lanes={lanes} />
    </>
  );
}

/** A 3px strip under the header. Each running agent is a dot of its colour gliding across. */
export function PulseBar({ live, lanes }: { live: boolean; lanes: PulseLane[] }) {
  const running = lanes.filter(l => l.running);
  return (
    <div className={`pulse${live ? ' is-live' : ''}`} aria-hidden="true">
      {live && running.length === 0 && <i className="comet" />}
      {running.map((l, i) => (
        <i key={l.id} className={`comet a-${l.agent}`} style={{ animationDelay: `${(i * 0.37) % 2.2}s`, animationDuration: `${2.2 + (i % 3) * 0.35}s` }} />
      ))}
    </div>
  );
}
