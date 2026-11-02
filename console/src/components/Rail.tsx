// Bento side rail: a live read of wiki/books/<me>.md (+ team.md for the manager).
import type { Rail as RailT } from '../../shared/protocol';
import { Ring, TierMix, Refs } from './Cards';

export function Rail({ rail, onSource, onPrompt, disabled }: { rail: RailT | null; onSource: (p: string) => void; onPrompt: (p: string) => void; disabled: boolean }) {
  if (!rail) return <aside className="rail" aria-label="My day at a glance"><div className="rcard muted">Loading your book…</div></aside>;
  const { book, team, windows } = rail;
  return (
    <aside className="rail" aria-label="My day at a glance">
      {rail.problem && <div className="problem">{rail.problem}</div>}
      {book && (
        <>
          <div className="rcard ring">
            <Ring done={book.meetings.done} target={book.meetings.target} />
            <div className="list" style={{ gap: 2 }}>
              <span className="h">Meetings this month</span>
              <span className="muted">{book.replies7d.replies} replies from {book.replies7d.sent} sent in 7 days</span>
            </div>
          </div>
          <div className="rcard">
            <span className="h">Book · {book.active} of {book.capacity ?? '–'}</span>
            <TierMix {...book.tiers} free={book.capacity != null ? Math.max(book.capacity - book.active, 0) : undefined} />
          </div>
          <div className="rcard dark">
            <span className="h">Hot ({book.hot.length})</span>
            {book.hot.length ? book.hot.slice(0, 5).map(h => (
              <button key={h.id} type="button" className="hotrow" style={{ background: 'none', border: 0, color: 'inherit', padding: 0, cursor: 'pointer', textAlign: 'left', minHeight: 28 }}
                onClick={() => onSource(`wiki/accounts/${h.id}.md`)}>
                <span>{h.name}</span><b>{h.tier}{/score ([\d.]+)/.exec(h.detail)?.[1] ? ` · ${/score ([\d.]+)/.exec(h.detail)![1]}` : ''}</b>
              </button>
            )) : <span className="dim">Nothing hot.</span>}
          </div>
          <div className="rcard">
            <span className="h">Due today ({book.due.length}) · at risk <span style={{ color: book.atRisk.length ? 'var(--risk)' : undefined }}>{book.atRisk.length}</span></span>
            {book.due.slice(0, 4).map(d => (
              <span key={d.id}><strong>{d.name}</strong> <span className="muted">· {d.action || d.nba}{d.overdue ? ' · overdue' : ''}</span></span>
            ))}
            {book.atRisk.slice(0, 3).map(a => <span key={a.id} className="muted"><strong style={{ color: 'var(--risk)' }}>{a.name}</strong> · {a.detail}</span>)}
            {!book.due.length && !book.atRisk.length && <span className="muted">Nothing due, nothing at risk.</span>}
            {book.vam.length > 0 && <span className="muted">{book.vam.length} VAM pre-draft{book.vam.length > 1 ? 's' : ''} waiting</span>}
          </div>
        </>
      )}
      {windows.map(w => (
        <div key={w.market} className={`rcard ${w.open ? 'green' : 'amber'}`}>
          <span className="h">{w.label}</span>
          <span style={{ fontSize: 14 }}>{w.market} · {w.detail}</span>
        </div>
      ))}
      {team && (
        <div className="rcard">
          <span className="h">Team · {team.reps} rep{team.reps === 1 ? '' : 's'}</span>
          <span><strong style={{ font: '800 28px var(--display)' }}>{team.pool.total}</strong> <span className="muted">in the pool · A {team.pool.A} · B {team.pool.B} · C {team.pool.C}</span></span>
          <span className="muted">Review queue: {team.review} undecided</span>
          <div className="row">
            <button type="button" className="btn primary" disabled={disabled} onClick={() => onPrompt('/mama-manager')}>Morning cockpit</button>
            <button type="button" className="btn" disabled={disabled} onClick={() => onPrompt('/mama-allocate')}>Allocate</button>
          </div>
        </div>
      )}
      {rail.bookPath && (
        <div className="rail-src">
          <Refs refs={[rail.bookPath, ...(team ? ['wiki/books/team.md'] : [])]} onSource={onSource} />
          {book?.generated && <span className="muted"> Built {book.generated}</span>}
        </div>
      )}
    </aside>
  );
}
