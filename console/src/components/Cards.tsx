// Renders mama-card blocks (docs/UI.md §2). Cards are views of wiki/raw/knowledge facts;
// buttons only send their prompt as the next turn.
import type { ReactNode } from 'react';
import type { Card as CardT, CardAction } from '../../shared/cards';

export interface CardCtx { onPrompt: (p: string) => void; onSource: (p: string) => void; disabled: boolean }

const AGENTS = ['mama', 'scout', 'researcher', 'vam', 'writer', 'allocator'];
const DEFAULT_AGENT: Record<string, string> = {
  draft: 'writer', reply: 'writer', allocation: 'allocator', review_queue: 'scout', agents: 'mama',
};
export const agentClass = (a?: string) => `a-${a && AGENTS.includes(a) ? a : 'mama'}`;
export const laneAgentClass = (subagentType: string) => agentClass(subagentType.toLowerCase());

const n = (v: unknown, d = 0) => (typeof v === 'number' && Number.isFinite(v) ? v : d);
const s = (v: unknown) => (v == null ? '' : typeof v === 'string' ? v : typeof v === 'number' || typeof v === 'boolean' ? String(v) : JSON.stringify(v));
const arr = <T = any,>(v: unknown): T[] => (Array.isArray(v) ? v : []);
const pct = (a: number, b: number) => (b > 0 ? Math.max(0, Math.min(100, (a / b) * 100)) : 0);
const label = (v: unknown) => (typeof v === 'object' && v ? s((v as any).account ?? (v as any).name ?? (v as any).id ?? JSON.stringify(v)) : s(v));

export function CardView({ card, issues, ctx }: { card: CardT; issues: string[]; ctx: CardCtx }) {
  const agent = card.agent ?? DEFAULT_AGENT[card.type];
  const Body = BODIES[card.type] ?? Fallback;
  const err = card.type === 'error';
  return (
    <article className={`card ${agentClass(agent)}${err ? ' err' : ''}`} aria-label={`${card.type} card: ${card.title}`}>
      <div className="card-head">
        <span className="t"><span className="tag">{err ? 'error' : agent ?? 'mama'}</span><span>{card.title}</span></span>
        {card.subtitle && <span className="sub">{card.subtitle}</span>}
      </div>
      <div className="card-body">
        <Body c={card} ctx={ctx} />
        {!!card.refs?.length && <Refs refs={card.refs} onSource={ctx.onSource} />}
      </div>
      {!!card.actions?.length && <Actions actions={card.actions} ctx={ctx} />}
      {issues.length > 0 && (
        <details className="issues">
          <summary>Shown best-effort: {issues.length} schema issue{issues.length > 1 ? 's' : ''} (cards.schema.json)</summary>
          <ul>{issues.map(i => <li key={i}>{i}</li>)}</ul>
        </details>
      )}
    </article>
  );
}

export function BadCard({ raw, issues }: { raw: string; issues: string[] }) {
  return (
    <article className="card err">
      <div className="card-head"><span className="t"><span className="tag">card</span><span>This card couldn't be read</span></span></div>
      <div className="card-body"><span className="muted">{issues.join('; ')}</span></div>
      <details className="issues"><summary>Raw block</summary><pre style={{ whiteSpace: 'pre-wrap' }}>{raw}</pre></details>
    </article>
  );
}

export function Refs({ refs, onSource }: { refs: string[]; onSource: (p: string) => void }) {
  return (
    <div className="refs" aria-label="Sources">
      {refs.map(r => <button key={r} type="button" className="ref" title={r} onClick={() => onSource(r)}>{r}</button>)}
    </div>
  );
}

function Actions({ actions, ctx }: { actions: CardAction[]; ctx: CardCtx }) {
  return (
    <div className="card-foot">
      {actions.map((a, i) => (
        <button key={a.label} type="button" disabled={ctx.disabled} title={a.prompt}
          className={`btn${a.style === 'primary' || (!a.style && i === 0) ? ' primary' : ''}`}
          onClick={() => ctx.onPrompt(a.prompt)}>{a.label}</button>
      ))}
    </div>
  );
}

type Body = (p: { c: CardT; ctx: CardCtx }) => ReactNode;

const StepDot = ({ status }: { status: string }) =>
  <span className={`dot ${status}`} aria-label={status}>{status === 'done' ? '✓' : status === 'failed' ? '!' : ''}</span>;

export const PlanList = ({ steps }: { steps: { label: string; status: string; agent?: string; note?: string }[] }) => (
  <div className="list">
    {steps.map((st, i) => (
      <div className="step" key={i}>
        <StepDot status={st.status} />
        <span className="grow">{st.label}{st.note && <span className="muted"> · {st.note}</span>}</span>
        {st.agent && <span className={`tag ${agentClass(st.agent.toLowerCase())}`}>{st.agent}</span>}
      </div>
    ))}
  </div>
);

const Tile = ({ k, v, f, cls = '', of: total, risk }: { k: string; v: ReactNode; f?: string; cls?: string; of?: number | null; risk?: boolean }) => (
  <div className={`tile ${cls}`}>
    <span className="k">{k}</span>
    <span className={`n${risk ? ' risk' : ''}`}>{v}{total != null && <small>/{total}</small>}</span>
    {f && <span className="f">{f}</span>}
  </div>
);

export const Ring = ({ done, target, size = 96 }: { done: number; target: number | null; size?: number }) => {
  const r = 36, c = 2 * Math.PI * r, p = target ? Math.min(done / target, 1) : 0;
  return (
    <svg role="img" aria-label={`${done} of ${target ?? '?'} meetings`} width={size} height={size} viewBox="0 0 96 96">
      <circle cx="48" cy="48" r={r} fill="none" stroke="var(--mama-t)" strokeWidth="12" />
      <circle cx="48" cy="48" r={r} fill="none" stroke="var(--mama)" strokeWidth="12" strokeLinecap="round"
        strokeDasharray={`${c * p} ${c}`} transform="rotate(-90 48 48)" />
      <text x="48" y="55" textAnchor="middle" fontFamily="Bricolage Grotesque, sans-serif" fontWeight="800" fontSize="22" fill="var(--ink)">{done}/{target ?? '–'}</text>
    </svg>
  );
};

export const TierMix = ({ A, B, C, free }: { A: number; B: number; C: number; free?: number }) => (
  <>
    <div className="mix" role="img" aria-label={`Tier A ${A}, B ${B}, C ${C}`}>
      <span style={{ flex: A, background: 'var(--mama)' }} /><span style={{ flex: B, background: 'var(--scout)' }} />
      <span style={{ flex: C, background: '#CFC9E0' }} />{free ? <span style={{ flex: free }} /> : null}
    </div>
    <div className="row muted"><span><b>A</b> {A}</span><span><b>B</b> {B}</span><span><b>C</b> {C}</span>{free != null && <span>{free} slots free</span>}</div>
  </>
);

const Plan: Body = ({ c }) => <PlanList steps={arr(c.steps).map((st: any) => ({ label: s(st.label), status: s(st.status), agent: st.agent, note: st.note }))} />;

const Agents: Body = ({ c }) => {
  const lanes = arr(c.lanes);
  if (!lanes.length) return <span className="empty">{s(c.note) || 'No agents ran.'}</span>;
  return (
    <div className="lanes">
      {lanes.map((l: any, i) => {
        const p = pct(n(l.done), n(l.total));
        return (
          <div className={`lane ${laneAgentClass(s(l.agent))}`} key={i}>
            <span className="tag">{s(l.agent)}</span>
            <span className="label">{s(l.label)}</span>
            <span className={`track${l.status === 'done' ? ' full' : l.status === 'failed' ? ' fail' : ''}`}><span style={{ width: `${l.status === 'done' ? 100 : p}%` }} /></span>
            <span className="state">{l.total ? `${n(l.done)}/${n(l.total)}` : s(l.status)}</span>
          </div>
        );
      })}
    </div>
  );
};

const DaySummary: Body = ({ c }) => {
  const hot = arr(c.hot), needs = arr(c.needs_you);
  return (
    <>
      <div className="tiles">
        <Tile k="Drafts ready" v={n(c.drafts)} f="to review" cls="a-writer" />
        <Tile k="Hot" v={hot.length} f={hot.some((h: any) => n(h.delta) > 0) ? "score jumps" : "accounts"} cls="dark" />
        <Tile k="At risk" v={n(c.at_risk)} cls="a-vam" risk={n(c.at_risk) > 0} />
        {c.send_window ? <Tile k="Send window" v={<span style={{ fontSize: 18 }}>{s(c.send_window)}</span>} cls="a-allocator" /> : null}
      </div>
      {hot.length > 0 && (
        <div className="list">
          {hot.map((h: any, i) => (
            <div className="row between" key={i}>
              <span><strong>{label(h)}</strong>{h.signal && <span className="muted"> · {s(h.signal)}</span>}</span>
              {typeof h.delta === 'number' && h.delta !== 0 && <strong style={{ color: 'var(--allocator)' }}>{h.delta > 0 ? '+' : ''}{h.delta.toFixed(2)}</strong>}
            </div>
          ))}
        </div>
      )}
      {needs.length > 0 && (
        <div className="list">
          <strong>Needs you</strong>
          {needs.map((x: any, i) => <span key={i}><strong>{s(x.account)}</strong> {s(x.text)}</span>)}
        </div>
      )}
    </>
  );
};

const Draft: Body = ({ c }) => (
  <>
    {c.to ? <span className="muted">To: {s(c.to)} · {s(c.channel)}</span> : <span className="muted">{s(c.channel)} · {s(c.account)}</span>}
    {c.subject ? <strong style={{ fontSize: 16 }}>{s(c.subject)}</strong> : null}
    <p className="draft-body">{s(c.body)}</p>
    <div className="refs">
      {c.signal ? <span className="tagchip a-scout">signal · {s(c.signal)}</span> : null}
      {c.pattern ? <span className="tagchip a-mama">pattern · {s(c.pattern)}</span> : null}
      {arr(c.checks).length > 0 && <span className="tagchip a-allocator">checks · {arr(c.checks).map(s).join(' ')}</span>}
    </div>
    {c.send_window ? <span className="muted">Send window: {s(c.send_window)}. You send it from your mailbox.</span> : null}
  </>
);

const REPLY_CLASS: Record<string, string> = {
  interested: 'a-allocator', meeting_request: 'a-allocator', referral: 'a-scout', objection: 'a-writer',
  not_now: 'a-writer', wrong_person: 'a-scout', unsubscribe: 'a-vam', bounce: 'a-vam', out_of_office: 'a-mama',
};
const Reply: Body = ({ c, ctx }) => (
  <>
    <div className="row">
      <span className={`tagchip ${REPLY_CLASS[s(c.class)] ?? 'a-mama'}`}>{s(c.class).replace(/_/g, ' ')}</span>
      <strong>{s(c.account)}</strong>{c.from ? <span className="muted">from {s(c.from)}</span> : null}
    </div>
    {c.summary ? <p style={{ margin: 0 }}>{s(c.summary)}</p> : null}
    {c.response_ref ? <Refs refs={[s(c.response_ref)]} onSource={ctx.onSource} /> : null}
  </>
);

const Book: Body = ({ c }) => {
  const tiers = (c.tiers ?? {}) as any, m = (c.meetings ?? {}) as any, r = (c.replies_7d ?? {}) as any;
  const active = n(c.active), cap = n(c.capacity);
  const rate = n(r.sent) ? Math.round((n(r.replies) / n(r.sent)) * 100) : null;
  const list = (title: string, items: unknown[], cls = '') => (
    <div className={`tile ${cls}`} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span className="k">{title}</span>
      {items.length ? items.map((x, i) => <span key={i}>{label(x)}</span>) : <span className="f">None</span>}
    </div>
  );
  return (
    <>
      <div className="tiles">
        <Tile k="Active accounts" v={active} of={cap} f={`${Math.max(cap - active, 0)} slots free`} />
        <div className="tile ring"><Ring done={n(m.done)} target={m.target ?? null} size={84} /><span className="k">Meetings<br />this month</span></div>
        <Tile k="Reply rate · 7 days" v={rate == null ? '–' : `${rate}%`} f={`${n(r.replies)} replies from ${n(r.sent)} sent`} cls="a-allocator" />
      </div>
      <TierMix A={n(tiers.A)} B={n(tiers.B)} C={n(tiers.C)} />
      <div className="tiles">
        {list('Today', arr(c.today), 'a-mama')}
        {list('Hot', arr(c.hot), 'dark')}
        {list('At risk', arr(c.at_risk), 'a-vam')}
      </div>
    </>
  );
};

const Donut = ({ score, tier }: { score: number; tier?: string }) => {
  const r = 36, c = 2 * Math.PI * r;
  return (
    <svg role="img" aria-label={`Score ${score.toFixed(2)}${tier ? `, tier ${tier}` : ''}`} width="96" height="96" viewBox="0 0 96 96">
      <circle cx="48" cy="48" r={r} fill="none" stroke="var(--mama-t)" strokeWidth="12" />
      <circle cx="48" cy="48" r={r} fill="none" stroke="var(--mama)" strokeWidth="12" strokeLinecap="round" strokeDasharray={`${c * score} ${c}`} transform="rotate(-90 48 48)" />
      <text x="48" y="54" textAnchor="middle" fontFamily="Bricolage Grotesque, sans-serif" fontWeight="800" fontSize="20" fill="var(--ink)">{score.toFixed(2)}</text>
    </svg>
  );
};

const Account: Body = ({ c, ctx }) => {
  const rec = (c.recommendation ?? {}) as any, next = (c.next ?? {}) as any, parts = (c.score_parts ?? {}) as Record<string, unknown>;
  return (
    <>
      <div className="row between">
        <div className="list" style={{ gap: 6 }}>
          <strong style={{ font: '800 22px var(--display)' }}>{s(c.name)}</strong>
          <div className="refs">
            <span className="tagchip">{s(c.market)}</span>
            {c.stage ? <span className="tagchip">Stage · {s(c.stage)}</span> : null}
            {c.owner ? <span className="tagchip">Owner {s(c.owner)}</span> : <span className="tagchip">Pool</span>}
          </div>
        </div>
        {typeof c.score === 'number' && <div className="row"><Donut score={c.score} tier={s(c.tier)} />{c.tier ? <span className="tag">Tier {s(c.tier)}</span> : null}</div>}
      </div>
      {Object.keys(parts).length > 0 && (
        <div className="list">
          <strong>What makes the score</strong>
          {Object.entries(parts).map(([k, v]) => (
            <div className="row" key={k}><span style={{ flex: '0 0 110px' }}>{k}</span><span className="bar"><span style={{ width: `${n(v) * 100}%` }} /></span><span style={{ flex: '0 0 40px', textAlign: 'right' }}>{n(v).toFixed(2)}</span></div>
          ))}
        </div>
      )}
      {arr(c.signals).length > 0 && (
        <div className="timeline">
          <strong>Signals · why now</strong>
          {arr(c.signals).map((sg: any, i) => (
            <div className="ev" key={i}><span className="pin" />
              <div className="list" style={{ gap: 4 }}>
                <span>{sg.date && <span className="muted">{s(sg.date)} · </span>}{s(sg.evidence) || s(sg.term)}</span>
                <div className="refs"><span className="tagchip a-scout">{s(sg.term)}</span>{sg.ref && <button type="button" className="ref" onClick={() => ctx.onSource(s(sg.ref))}>{s(sg.ref)}</button>}</div>
              </div>
            </div>
          ))}
        </div>
      )}
      {(arr(rec.chain).length > 0 || rec.product) && (
        <div className="list">
          <strong>Recommendation</strong>
          <div className="chain">
            {[...arr(rec.chain).map(s), ...(rec.product ? [s(rec.product)] : []), ...(rec.proof ? [`proof · ${s(rec.proof)}`] : [])]
              .flatMap((x, i) => (i ? [<span key={`a${i}`} className="arrow" aria-hidden="true">→</span>] : []).concat(<span key={i} className="tagchip">{x}</span>))}
          </div>
          {rec.talk_track && <p className="quote">“{s(rec.talk_track)}”</p>}
        </div>
      )}
      {next.action && <div className="tile a-vam"><span className="k">Next best action{next.due ? ` · due ${s(next.due)}` : ''}</span><span>{s(next.action)}</span></div>}
    </>
  );
};

const Brief: Body = ({ c }) => (
  <>
    {c.subject ? <span className="muted">{s(c.subject)}</span> : null}
    {arr(c.sections).map((sec: any, i) => (
      <div key={i} className="list" style={{ gap: 4 }}>
        <strong>{s(sec.heading)}</strong>
        <ul style={{ margin: 0, paddingLeft: 20 }}>{arr(sec.bullets).map((b, j) => <li key={j}>{s(b)}</li>)}</ul>
      </div>
    ))}
  </>
);

const initials = (x: string) => x.split(/[\s._-]+/).filter(Boolean).slice(0, 2).map(w => w[0]!.toUpperCase()).join('');

const Allocation: Body = ({ c }) => {
  const rows = arr(c.rows), max = Math.max(1, ...rows.map((r: any) => n(r.ev)));
  return (
    <>
      <div className="row muted">
        {c.total != null && <span><strong style={{ color: 'var(--ink)' }}>{n(c.total)} leads</strong> → {rows.length} rep{rows.length === 1 ? '' : 's'}</span>}
        {c.spread != null && <span>EV spread {Math.round(n(c.spread) * 100)}%{c.limit != null ? ` · limit ${Math.round(n(c.limit) * 100)}%` : ''}</span>}
      </div>
      <div className="list">
        {rows.map((r: any, i) => (
          <div className="row" key={i}>
            <span className="avatar" style={{ background: 'var(--allocator)' }} aria-hidden="true">{initials(s(r.rep))}</span>
            <span style={{ flex: '0 0 150px' }}><strong>{s(r.rep)}</strong><br /><span className="muted">{s(r.market)} · A {n(r.leads_a)} · B {n(r.leads_b)}</span></span>
            <span className="bar" style={{ flex: '1 1 100px' }}><span style={{ width: `${pct(n(r.ev), max)}%` }} /></span>
            <span style={{ flex: '0 0 auto', fontWeight: 700 }}>{r.ev != null ? `${s(r.currency)} ${n(r.ev).toLocaleString()}` : ''}</span>
            <span className="muted" style={{ flex: '1 1 100%' }}>{s(r.why)}</span>
          </div>
        ))}
      </div>
      <span className="muted">Nothing is assigned until you approve.</span>
    </>
  );
};

const ReviewQueue: Body = ({ c }) => {
  const items = arr(c.items);
  if (!items.length) return <span className="empty">Nothing to review.</span>;
  return (
    <div className="list">
      {items.map((it: any, i) => (
        <div className="row" key={i}>
          <span className="grow">{it.n != null && <strong>#{n(it.n)} </strong>}“{s(it.text)}” {it.source && <span className="muted">({s(it.source)})</span>} → <strong>{s(it.candidate)}</strong></span>
          {typeof it.confidence === 'number' && <span className="row" style={{ flex: '0 0 140px' }}><span className="bar"><span style={{ width: `${it.confidence * 100}%` }} /></span>{it.confidence.toFixed(2)}</span>}
        </div>
      ))}
    </div>
  );
};

const RunStatus: Body = ({ c }) => {
  const stat = (k: string, v: unknown) => <Tile k={k} v={typeof v === 'number' ? v : '–'} />;
  return (
    <>
      <div className="row">
        <span className={`live${c.ok ? ' idle' : ''}`} style={{ background: c.ok ? 'var(--allocator)' : 'var(--risk)' }} />
        <strong>{c.ok ? 'All clear' : 'Needs attention'}</strong>
        {(c.started || c.finished) ? <span className="muted">{s(c.started)}{c.finished ? ` – ${s(c.finished)}` : ''}</span> : null}
        {arr(c.markets).map(m => <span key={s(m)} className="tagchip">{s(m)}</span>)}
      </div>
      <div className="tiles">
        {stat('Items', c.items)}{stat('Linked', c.linked)}{stat('Review', c.review)}{stat('New leads', c.new_leads)}
        {typeof c.errors === 'number' ? <Tile k="Errors" v={c.errors} risk={c.errors > 0} cls="a-vam" /> : null}
      </div>
      {typeof c.errors === 'string' && <span className="muted"><strong>Errors:</strong> {c.errors}</span>}
    </>
  );
};

const TeamBook: Body = ({ c }) => {
  const pool = (c.pool ?? {}) as any;
  return (
    <div className="list">
      {arr(c.rows).map((r: any, i) => (
        <div className="row" key={i}>
          <span className="avatar" aria-hidden="true">{initials(s(r.rep))}</span>
          <span style={{ flex: '0 0 120px' }}><strong>{s(r.rep)}</strong> <span className="muted">{s(r.market)}</span></span>
          <span style={{ flex: '0 0 110px' }}><strong>{n(r.meetings)}</strong><span className="muted">/{s(r.target ?? '–')} meetings</span></span>
          <span className="bar"><span style={{ width: `${pct(n(r.active), n(r.capacity))}%` }} /></span>
          <span className="muted" style={{ flex: '0 0 auto' }}>{n(r.active)}/{n(r.capacity)} active · <span style={{ color: n(r.at_risk) ? 'var(--risk)' : undefined }}>{n(r.at_risk)} at risk</span></span>
        </div>
      ))}
      {Object.keys(pool).length > 0 && (
        <div className="tile">
          <span className="k">Pool</span>
          <span className="n">{n(pool.a) + n(pool.b) + n(pool.c)}<small> unallocated</small></span>
          <span className="f">A {n(pool.a)} · B {n(pool.b)} · C {n(pool.c)}</span>
        </div>
      )}
    </div>
  );
};

const ErrorBody: Body = ({ c }) => (
  <>
    <span>{s(c.message)}</span>
    {c.fix ? <span className="muted"><strong>Fix:</strong> {s(c.fix)}</span> : null}
  </>
);

const Fallback: Body = ({ c }) => {
  const { type, title, subtitle, agent, refs, actions, ...rest } = c;
  return <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'var(--mono)', fontSize: 12 }}>{JSON.stringify(rest, null, 2)}</pre>;
};

const BODIES: Record<string, Body> = {
  plan: Plan, agents: Agents, day_summary: DaySummary, draft: Draft, reply: Reply, book: Book,
  account: Account, brief: Brief, allocation: Allocation, review_queue: ReviewQueue,
  run_status: RunStatus, team_book: TeamBook, error: ErrorBody,
};
