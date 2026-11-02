// Parser tests against real recorded streams (record more with `npm run record -- <skill>`).
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { TurnBuilder, describeTool, parseLines, relPath, type StreamEvent } from '../shared/stream';
import { cardsIn, splitCards } from '../shared/cards';

const load = (name: string) => parseLines(readFileSync(join(__dirname, 'fixtures', `${name}.jsonl`), 'utf8'));
const finalResult = (events: StreamEvent[]) => events.find(e => e.type === 'result')!;
const build = (events: StreamEvent[]) => { const b = new TurnBuilder(); b.applyAll(events); return b; };

const SKILLS = ['mama-book', 'mama-manager', 'mama-day'] as const;

describe.each(SKILLS)('%s recording', name => {
  const events = load(name);
  const b = build(events);
  const turn = b.turn;
  const result = finalResult(events);

  it('finishes with the session id from the result', () => {
    expect(turn.done).toBe(true);
    expect(turn.result?.ok).toBe(true);
    expect(turn.sessionId).toBe(result.session_id);
  });

  it('streams the same final answer the CLI reports', () => {
    const texts = turn.items.filter(i => i.kind === 'text');
    expect(texts.at(-1)!.text.trim()).toBe(String(result.result).trim());
    expect(texts.every(t => t.done)).toBe(true);
  });

  it('builds the same text without partial messages', () => {
    const whole = build(events.filter(e => e.type !== 'stream_event'));
    expect(whole.text()).toBe(b.text());
  });

  it('has one chip per main-agent tool call and none left running', () => {
    const ids = events.filter(e => e.type === 'assistant' && !e.parent_tool_use_id)
      .flatMap(e => e.message.content).filter((c: any) => c.type === 'tool_use').map((c: any) => c.id);
    const chips = turn.items.filter(i => i.kind === 'tool');
    expect(chips.map(c => c.id)).toEqual(ids);
    expect(chips.some(c => c.status === 'running')).toBe(false);
  });

  it('marks every permission denial on its chip', () => {
    const denied = events.filter(e => e.type === 'system' && e.subtype === 'permission_denied');
    expect(turn.denied).toHaveLength(denied.length);
    for (const d of denied) {
      expect(turn.items.find(i => i.id === d.tool_use_id)).toMatchObject({ status: 'denied' });
    }
  });

  it('records the SessionStart hook', () => {
    expect(turn.hooks).toContain('SessionStart:startup');
  });

  it('shows a pending card while a fence is still streaming', () => {
    const live = new TurnBuilder();
    let sawPending = false;
    for (const e of events) {
      live.apply(e);
      if (splitCards(live.text()).some(p => p.kind === 'pending')) sawPending = true;
    }
    expect(sawPending).toBe(true);
    expect(splitCards(live.text()).some(p => p.kind === 'pending')).toBe(false);
  });
});

describe('cards in the recordings', () => {
  const cards = (name: string) => cardsIn(build(load(name)).text());
  const summary = (name: string) => cards(name).map(p => (p.kind === 'card' ? [p.card.type, p.issues.length === 0] : ['bad', false]));

  it('mama-book emits one valid book card', () => {
    expect(summary('mama-book')).toEqual([['book', true]]);
    const [p] = cards('mama-book');
    expect(p.kind === 'card' && p.card.refs).toContain('wiki/books/praveen.md');
  });

  it('mama-day emits plan, agents and day_summary; the plan uses an off-schema status', () => {
    expect(summary('mama-day')).toEqual([['plan', false], ['agents', true], ['day_summary', true]]);
    const [plan] = cards('mama-day');
    expect(plan.issues.join(' ')).toMatch(/status must be equal to one of the allowed values/);
  });

  it('mama-manager emits the cockpit cards; run_status.errors is a string, not a count', () => {
    expect(summary('mama-manager')).toEqual([['run_status', false], ['allocation', true], ['review_queue', true], ['team_book', true]]);
    const [run] = cards('mama-manager');
    expect(run.issues).toContain('/errors must be integer');
  });

  it('keeps card actions as prompts for the next turn', () => {
    const alloc = cards('mama-manager')[1];
    expect(alloc.kind === 'card' && alloc.card.actions?.map(a => a.prompt)).toEqual(['approve all', 'approve except 10, 11, 12, 13, 14 and 15']);
  });
});

describe('subagent lanes (probe recording)', () => {
  const events = load('subagent-probe');
  const turn = build(events).turn;

  it('opens one lane per Agent call, keyed by parent_tool_use_id', () => {
    expect(turn.lanes).toHaveLength(1);
    const [lane] = turn.lanes;
    const sub = events.find(e => e.parent_tool_use_id)!;
    expect(lane).toMatchObject({ id: sub.parent_tool_use_id, agent: 'general-purpose', label: 'Count root directory entries', status: 'done', tools: 1 });
  });

  it('attributes the subagent denial to its lane, not a main chip', () => {
    expect(turn.lanes[0].last).toBe('Bash needs approval');
    expect(turn.items.filter(i => i.kind === 'tool')).toHaveLength(0);
    expect(turn.denied).toHaveLength(1);
  });

  it('keeps subagent text out of the main bubble', () => {
    const main = turn.items.filter(i => i.kind === 'text').map(i => (i as any).text).join('');
    expect(main).not.toContain('Run `ls /` with the Bash tool');
  });
});

describe('plan from todo tools', () => {
  const tool = (id: string, name: string, input: object) =>
    ({ type: 'assistant', parent_tool_use_id: null, message: { id: `m-${id}`, content: [{ type: 'tool_use', id, name, input }] } });
  const ok = (id: string, text: string) =>
    ({ type: 'user', parent_tool_use_id: null, message: { content: [{ type: 'tool_result', tool_use_id: id, content: text }] } });

  it('reads TodoWrite lists', () => {
    const turn = build([tool('t1', 'TodoWrite', { todos: [
      { content: 'Triage replies', status: 'completed' },
      { content: 'Research leads', status: 'in_progress' },
      { content: 'Write drafts', status: 'pending' },
    ] })]).turn;
    expect(turn.plan.map(s => s.status)).toEqual(['done', 'running', 'pending']);
    expect(turn.items).toHaveLength(0); // plan tools don't show as chips
  });

  it('reads TaskCreate / TaskUpdate', () => {
    const turn = build([
      tool('a', 'TaskCreate', { subject: 'Scan sources' }), ok('a', 'Task #1 created successfully: Scan sources'),
      tool('b', 'TaskCreate', { subject: 'Score' }), ok('b', 'Task #2 created successfully: Score'),
      tool('c', 'TaskUpdate', { taskId: '2', status: 'in_progress' }),
      tool('d', 'TaskUpdate', { taskId: '1', status: 'completed' }),
    ]).turn;
    expect(turn.plan).toEqual([
      { id: '1', label: 'Scan sources', status: 'done' },
      { id: '2', label: 'Score', status: 'running' },
    ]);
  });
});

describe('tool chip labels', () => {
  it('names files and scripts relative to the repo', () => {
    expect(describeTool('Read', { file_path: '/Users/x/sales-mama.ai/wiki/accounts/acme.md' })).toBe('Reading wiki/accounts/acme.md');
    expect(describeTool('Bash', { command: 'python3 scripts/score.py --all', description: 'Score' })).toBe('Running scripts/score.py');
    expect(describeTool('Bash', { command: 'git status', description: 'Show status' })).toBe('Show status');
    expect(describeTool('mcp__claude_ai_Gmail__create_draft', {})).toBe('Gmail · create draft');
    expect(relPath('/r/repo/knowledge/x.yaml', '/r/repo')).toBe('knowledge/x.yaml');
  });
});
