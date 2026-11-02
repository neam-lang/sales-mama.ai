import { Fragment } from 'react';
import { describeTool, type Item, type Lane, type ToolItem } from '../../shared/stream';
import { splitCards } from '../../shared/cards';
import type { ChatTurn } from '../useBridge';
import { BadCard, CardView, PlanList, laneAgentClass, type CardCtx } from './Cards';
import { Markdown } from './Markdown';

export function TurnView({ t, ctx }: { t: ChatTurn; ctx: CardCtx }) {
  const { turn } = t;
  const groups = group(turn.items);
  const lastText = [...turn.items].reverse().find(i => i.kind === 'text');
  const thinking = t.running && !turn.items.length && !turn.lanes.length;
  return (
    <>
      <div className={`you${t.prompt.startsWith('/') ? ' cmd' : ''}`}>{t.prompt}</div>
      <div className="mama-row">
        <span className="mama-dot" aria-hidden="true">M</span>
        <div className="mama-body" aria-live="polite" aria-busy={t.running}>
          {thinking && <p className="md caret" style={{ marginTop: 6 }}>{turn.hooks.length ? 'Starting session…' : 'Thinking…'}</p>}
          {turn.plan.length > 0 && (
            <section className="plan" aria-label="Plan">
              <div className="row between"><strong>Plan · {turn.plan.length} steps</strong><span className="muted">{planSummary(turn.plan)}</span></div>
              <PlanList steps={turn.plan} />
            </section>
          )}
          {turn.lanes.length > 0 && <Lanes lanes={turn.lanes} />}
          {groups.map((g, gi) => (
            <Fragment key={gi}>
              {g.kind === 'tools'
                ? <Chips tools={g.tools} />
                : splitCards(g.item.text).map((p, i) =>
                    p.kind === 'md' ? <Markdown key={i} text={p.text} onSource={ctx.onSource} streaming={t.running && g.item === lastText && !g.item.done} />
                    : p.kind === 'card' ? <CardView key={i} card={p.card} issues={p.issues} ctx={ctx} />
                    : p.kind === 'bad' ? <BadCard key={i} raw={p.raw} issues={p.issues} />
                    : <div key={i} className="pending-card">Building a card…</div>)}
            </Fragment>
          ))}
          {turn.denied.length > 0 && !t.running && <NeedsApproval denied={turn.denied} />}
          {t.error && (
            <CardView card={{ type: 'error', title: 'The run stopped', message: t.error.message, fix: t.error.fix }} issues={[]} ctx={ctx} />
          )}
          {turn.result && !turn.result.ok && !t.error && (
            <CardView card={{ type: 'error', title: 'The run ended with an error', message: turn.result.error ?? 'Unknown error', fix: 'Run the same prompt in Claude Code to see the details.' }} issues={[]} ctx={ctx} />
          )}
          {turn.result && (
            <span className="muted">
              {turn.result.durationMs != null && `${Math.round(turn.result.durationMs / 1000)} s`}
              {turn.result.turns != null && ` · ${turn.result.turns} steps`}
              {turn.result.costUsd != null && ` · $${turn.result.costUsd.toFixed(2)}`}
            </span>
          )}
        </div>
      </div>
    </>
  );
}

function planSummary(plan: { status: string }[]) {
  const c = (s: string) => plan.filter(p => p.status === s).length;
  return [`${c('done')} done`, c('running') && `${c('running')} running`, c('pending') && `${c('pending')} queued`, c('failed') && `${c('failed')} failed`].filter(Boolean).join(' · ');
}

function Lanes({ lanes }: { lanes: Lane[] }) {
  const running = lanes.filter(l => l.status === 'running').length;
  return (
    <section className="lanes" aria-label="Agents working">
      <div className="row">
        <span className={`live${running ? '' : ' idle'}`} aria-hidden="true" />
        <strong>{running ? 'Agents working' : 'Agents finished'}</strong>
        <span className="dim">{running ? `${running} running${lanes.length > running ? ` · ${lanes.length - running} done` : ''}` : `${lanes.length} ran`}</span>
      </div>
      {lanes.map(l => (
        <div key={l.id} className={`lane ${laneAgentClass(l.agent)}`}>
          <span className="tag">{l.agent}</span>
          <span className="label">{l.label}{l.last && <span className="last">{l.last}</span>}</span>
          <span className={`track ${l.status === 'running' ? 'indet' : l.status === 'done' ? 'full' : 'fail'}`}><span /></span>
          <span className="state">{l.status === 'running' ? `${l.tools} tool${l.tools === 1 ? '' : 's'}` : l.status}</span>
        </div>
      ))}
    </section>
  );
}

function Chips({ tools }: { tools: ToolItem[] }) {
  return (
    <div className="chips" aria-label="Tools used">
      {tools.map(c => {
        const text = describeTool(c.name, c.input);
        return (
          <span key={c.id} className={`chip ${c.status}`} title={c.note ?? text}>
            <span className="s" aria-label={c.status} />{text}
          </span>
        );
      })}
    </div>
  );
}

function NeedsApproval({ denied }: { denied: string[] }) {
  return (
    <article className="card a-writer" aria-label="Needs approval">
      <div className="card-head"><span className="t"><span className="tag">permissions</span><span>{denied.length} step{denied.length > 1 ? 's' : ''} needed your approval</span></span></div>
      <div className="card-body">
        <span>The console runs with this repo's permission settings and never widens them, so these were skipped:</span>
        <ul style={{ margin: 0, paddingLeft: 20, fontFamily: 'var(--mono)', fontSize: 12 }}>{[...new Set(denied)].slice(0, 6).map(d => <li key={d}>{d}</li>)}</ul>
        <span className="muted"><strong>Fix:</strong> run this in Claude Code and approve them there, or ask your manager to add allow rules for the Sales Mama scripts in <code>.claude/settings.json</code>.</span>
      </div>
    </article>
  );
}

type Group = { kind: 'tools'; tools: ToolItem[] } | { kind: 'text'; item: Extract<Item, { kind: 'text' }> };
function group(items: Item[]): Group[] {
  const out: Group[] = [];
  for (const it of items) {
    if (it.kind === 'tool') {
      const last = out[out.length - 1];
      if (last?.kind === 'tools') last.tools.push(it); else out.push({ kind: 'tools', tools: [it] });
    } else if (it.text.trim()) out.push({ kind: 'text', item: it });
  }
  return out;
}
