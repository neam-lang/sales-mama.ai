// Chat: the thread scrolls on its own; the composer is docked under it, never over it (spec §4–5).
import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { AccountInfo, SkillInfo } from '../../server/repo';
import type { ChatTurn } from '../useBridge';
import { useStickToBottom } from '../useStickToBottom';
import { TurnView } from '../chat/Turn';
import { Composer } from '../chat/Composer';
import { followUpsFor } from '../chat/followups';
import { loadChats, removeChat, type SavedChat } from '../chat/history';
import type { CardCtx } from '../components/Cards';
import { IconDown } from './Icons';

export function ChatView({ turns, ctx, manager, firstName, canAsk, live, ask, stop, seed, onSeedUsed, skills, accounts, queued, onQueue, onCancelQueue, onOpenChat, voiceSlot, voiceAbove }: {
  turns: ChatTurn[]; ctx: CardCtx; manager: boolean; firstName: string; canAsk: boolean; live: boolean;
  ask: (t: string) => void; stop: () => void; seed: string | null; onSeedUsed: () => void;
  skills: SkillInfo[]; accounts: AccountInfo[]; queued: string | null; onQueue: (t: string) => void; onCancelQueue: () => void;
  onOpenChat: (c: SavedChat) => void; voiceSlot?: ReactNode; voiceAbove?: ReactNode;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const { showJump, jump } = useStickToBottom(scrollRef, contentRef, turns.length);
  useEffect(() => {
    window.addEventListener('mama:jump', jump);
    return () => window.removeEventListener('mama:jump', jump);
  }, [jump]);
  const followUps = followUpsFor(turns[turns.length - 1]);
  return (
    <section className="chat-view" aria-label="Chat">
      <div className="thread" ref={scrollRef}>
        <div className="thread-col" ref={contentRef}>
          {turns.length === 0 && <ChatEmpty manager={manager} firstName={firstName} canAsk={canAsk} ask={ask} onOpenChat={onOpenChat} />}
          {turns.map(t => <TurnView key={t.id} t={t} ctx={ctx} />)}
        </div>
      </div>
      <div className="dock-wrap">
        {showJump && (
          <button type="button" className="jump" onClick={jump} aria-label="Jump to the latest message (⌘↓)">
            <IconDown size={14} />{live ? 'New activity' : 'Jump to latest'}
          </button>
        )}
        <Composer inputId="composer" manager={manager} skills={skills} accounts={accounts} live={live} canAsk={canAsk} ask={ask} stop={stop}
          queued={queued} onQueue={onQueue} onCancelQueue={onCancelQueue} followUps={followUps} seed={seed} onSeedUsed={onSeedUsed}
          voiceSlot={voiceSlot} above={voiceAbove} />
      </div>
    </section>
  );
}

function ChatEmpty({ manager, firstName, canAsk, ask, onOpenChat }: {
  manager: boolean; firstName: string; canAsk: boolean; ask: (t: string) => void; onOpenChat: (c: SavedChat) => void;
}) {
  const [chats, setChats] = useState<SavedChat[]>(loadChats);
  useEffect(() => {
    const sync = () => setChats(loadChats());
    window.addEventListener('mama:history', sync);
    return () => window.removeEventListener('mama:history', sync);
  }, []);
  const quick = manager
    ? ['/mama-manager', '/company-insights segment --industry clinics', '/mama-weekly', 'What changed overnight?']
    : ['/mama-day', '/mama-book', '/company-check', 'What changed overnight?'];
  const when = (iso: string) => new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(iso));
  return (
    <div className="chat-empty">
      <span className="logo big" aria-hidden="true">SM</span>
      <h1>What shall we work on{firstName ? `, ${firstName}` : ''}?</h1>
      <p>{manager ? 'Run the cockpit, review the team, or ask about any account.' : 'Run your day, check a company, or ask about your book.'}</p>
      <div className="quick">
        {quick.map((q, i) => <button key={q} type="button" style={{ animationDelay: `${60 + i * 50}ms` }} disabled={!canAsk} onClick={() => ask(q)}>{q}</button>)}
      </div>
      {chats.length > 0 && (
        <section className="recent" aria-label="Recent chats">
          <h2 className="sec">Recent chats</h2>
          <ul>
            {chats.slice(0, 6).map((c, i) => (
              <li key={c.id} style={{ animationDelay: `${120 + i * 40}ms` }}>
                <button type="button" className="recent-open" onClick={() => onOpenChat(c)}>
                  <span className="r-title">{c.title}</span>
                  <span className="r-meta">{c.turns.length} turn{c.turns.length === 1 ? '' : 's'} · {when(c.updated)}</span>
                </button>
                <button type="button" className="recent-del" onClick={() => removeChat(c.id)} aria-label={`Forget "${c.title}"`} title="Forget this chat">×</button>
              </li>
            ))}
          </ul>
          <p className="r-note">Kept in this browser only.</p>
        </section>
      )}
    </div>
  );
}
