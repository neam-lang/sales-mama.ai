import { mkdtempSync, mkdirSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { buildArgs, FORBIDDEN_FLAGS } from '../server/engine';
import { readSource, readData } from '../server/repo';
import { parseCard, safeActions, splitCards } from '../shared/cards';
import { bookFromJson, teamFromJson } from '../shared/book';
import { sendWindow } from '../shared/window';

describe('engine args (ADR-0006)', () => {
  const sid = '35a18c32-0dd1-4769-804f-f36268b15b05';

  it('runs exactly the documented command', () => {
    expect(buildArgs('/mama-day', sid)).toEqual([
      '-p', '--output-format', 'stream-json', '--verbose', '--include-partial-messages',
      '--append-system-prompt', 'MAMA_CARDS=on', '--resume', sid, '--', '/mama-day',
    ]);
  });

  it('never passes a permission-widening flag, even if the prompt contains one', () => {
    const args = buildArgs('--dangerously-skip-permissions', sid);
    const flags = args.slice(0, args.indexOf('--'));
    for (const f of FORBIDDEN_FLAGS) expect(flags).not.toContain(f);
    expect(args.at(-1)).toBe('--dangerously-skip-permissions'); // after "--", so it is prompt text
  });

  it('drops a session id that is not a uuid', () => {
    expect(buildArgs('hi', '--settings evil.json')).not.toContain('--resume');
    expect(buildArgs('hi')).not.toContain('--resume');
  });

  it('skipping permissions is off by default and only the owner\'s opt-in turns it on', () => {
    expect(buildArgs('hi', undefined, false, false)).not.toContain('--dangerously-skip-permissions');
    const on = buildArgs('hi', undefined, false, true);
    expect(on).toContain('--dangerously-skip-permissions');
    expect(on.indexOf('--dangerously-skip-permissions')).toBeLessThan(on.indexOf('--'));
    expect(on.at(-1)).toBe('hi');
  });

  it('voice adds only guidance to the system prompt, never a flag', () => {
    const args = buildArgs('brief me', undefined, true);
    const i = args.indexOf('--append-system-prompt');
    expect(args[i + 1]).toMatch(/^MAMA_CARDS=on\nMAMA_VOICE=on\. /);
    expect(args[i + 1]).toMatch(/under 25 words/);
    expect(args.filter(a => a.startsWith('--')).sort()).toEqual(buildArgs('brief me').filter(a => a.startsWith('--')).sort());
    for (const f of FORBIDDEN_FLAGS) expect(args).not.toContain(f);
  });
});

describe('cards', () => {
  it('splits markdown and cards in order', () => {
    const text = 'Summary line.\n\n```mama-card\n{"type":"error","title":"Oops","message":"x"}\n```\nAfter.';
    expect(splitCards(text).map(p => p.kind)).toEqual(['md', 'card', 'md']);
  });

  it('hides a half-typed fence', () => {
    expect(splitCards('Summary.\n\n```mama-ca')).toEqual([{ kind: 'md', text: 'Summary.\n\n' }]);
  });

  it('reports bad JSON and missing type/title', () => {
    expect(parseCard('{nope').kind).toBe('bad');
    expect(parseCard('{"type":"plan"}').kind).toBe('bad');
  });

  it('validates per-type required fields', () => {
    const p = parseCard('{"type":"draft","title":"x","account":"a","channel":"fax","body":"b"}');
    expect(p.kind === 'card' && p.issues).toEqual(expect.arrayContaining([
      "(card) must have required property 'checks'",
      expect.stringMatching(/^\/channel must be equal to one of the allowed values/),
    ]));
  });

  it('validates the analytics cards (company insights)', () => {
    const ok = [
      '{"type":"stats","title":"Clinics","tiles":[{"label":"Live","value":9618,"tone":"neutral"},{"label":"On time","value":92.7,"unit":"%","tone":"good"}]}',
      '{"type":"chart","title":"Per year","kind":"bar","series":[{"label":"2025","value":808}]}',
      '{"type":"chart","title":"Types","kind":"donut","series":[{"label":"Local Company","value":7166},{"label":"Other","value":2452}]}',
      '{"type":"table","title":"Leads","columns":[{"key":"name","label":"Company"},{"key":"rank","label":"Rank","align":"right"}],"rows":[{"name":"A","rank":43}]}',
      '{"type":"company","title":"SIA","uen":"197200078R","verdict":"Likely legitimate","score":80,"groups":[{"name":"Registry","checks":[{"id":"G2","check":"Live","result":"pass","detail":"Live Company"}]}]}',
      '{"type":"compare","title":"Side by side","companies":[{"name":"A","verdict":"Verified","score":90},{"name":"B","verdict":"Caution","score":40}],"rows":[{"check":"Status","values":[{"result":"pass","text":"Live"},{"result":"fail","text":"Struck Off"}]}]}',
    ];
    for (const raw of ok) {
      const p = parseCard(raw);
      expect(p.kind === 'card' && p.issues).toEqual([]);
    }
    const bad = parseCard('{"type":"chart","title":"x","kind":"pie","series":[]}');
    expect(bad.kind === 'card' && bad.issues).toEqual(expect.arrayContaining([expect.stringMatching(/^\/kind must be equal to one of the allowed values/)]));
    const noGroups = parseCard('{"type":"company","title":"x","uen":"1","verdict":"Caution","score":1}');
    expect(noGroups.kind === 'card' && noGroups.issues).toEqual(["(card) must have required property 'groups'"]);
  });

  it('never offers a send button', () => {
    expect(safeActions([
      { label: 'Send now', prompt: 'send it' },
      { label: 'Open in mailbox', prompt: 'open' },
      { label: 'Resend', prompt: 'x' },
      { label: 42, prompt: 'x' },
    ]).map(a => a.label)).toEqual(['Open in mailbox', 'Resend']);
  });
});

// Shapes written by scripts/build_books.py rep_data() / team_data() (wiki/books/<rep>.json, team.json).
const BOOK = {
  type: 'book', rep: 'mei', name: 'Mei Tan', role: 'rep', markets: ['SG', 'MY'], date: '2026-11-02', generated: '2026-11-02 17:04',
  active: 42, capacity: 60, quota: 15, tiers: { A: 9, B: 18, C: 15 }, meetings: 5, target: 8, sent_7: 31, replies_7: 6,
  meetings_7: 1, touches_7: 40, handed_over_month: 0,
  due: [{ account: 'bayfront-dental', name: 'Bayfront Dental', tier: 'A', due: '2026-11-01', overdue: true, next_action: 'first email', nba: 'email', nba_reason: 'new branch' }],
  hot: [{ account: 'bayfront-dental', name: 'Bayfront Dental', tier: 'A', score: 0.88, score_updated: '2026-11-02' }],
  at_risk: [], vam_predrafts: [], stages: { new: 30, researched: 12 },
};

describe('book data', () => {
  it('maps the rep book JSON for the rail', () => {
    const b = bookFromJson(BOOK);
    expect(b).toMatchObject({
      name: 'Mei Tan', rep: 'mei', role: 'rep', markets: ['SG', 'MY'], active: 42, capacity: 60,
      tiers: { A: 9, B: 18, C: 15 }, meetings: { done: 5, target: 8 }, replies7d: { replies: 6, sent: 31 },
      quota: 15, generated: '2026-11-02 17:04', atRisk: [], vam: [],
      pipeline: [{ stage: 'new', n: 30 }, { stage: 'researched', n: 12 }],
    });
    expect(b.due).toEqual([{ id: 'bayfront-dental', name: 'Bayfront Dental', tier: 'A', due: '2026-11-01', overdue: true, action: 'first email', nba: 'email', why: 'new branch' }]);
    expect(b.hot[0]).toEqual({ id: 'bayfront-dental', name: 'Bayfront Dental', tier: 'A', detail: 'score 0.88' });
  });

  it('maps the team book JSON', () => {
    const t = teamFromJson({ generated: '2026-11-02 17:04', reps: [{ rep: 'p' }], pool: { count: 77, tiers: { A: 7, B: 3, C: 67 } }, review_open: 2 });
    expect(t).toEqual({ generated: '2026-11-02 17:04', reps: 1, pool: { total: 77, A: 7, B: 3, C: 67 }, review: 2 });
  });

  it('tolerates a missing or partial file', () => {
    expect(bookFromJson({}).active).toBe(0);
    expect(teamFromJson({}).pool.total).toBe(0);
  });
});

describe('send window', () => {
  const SG = { tz: 'Asia/Singapore', send_windows: { days: ['mon', 'tue', 'wed', 'thu'], hours: '09:00-11:30' }, holidays: ['2026-11-09'] };
  const at = (iso: string) => sendWindow('SG', SG, new Date(iso));

  it('is open inside the window, in market time', () => {
    expect(at('2026-11-02T01:30:00Z')).toMatchObject({ open: true, label: 'Send window open · closes in 2h 0m' }); // Mon 09:30 SGT
  });
  it('counts down before it opens', () => {
    expect(at('2026-11-02T00:38:00Z').label).toBe('Send window opens in 22 min');
  });
  it('skips weekends and holidays', () => {
    expect(at('2026-11-05T05:00:00Z').label).toBe('Next send window Tue 10 09:00'); // Thu after window; Mon 9 is a holiday
    expect(at('2026-11-09T02:00:00Z').label).toBe('Next send window tomorrow 09:00 (holiday today)');
  });
});

describe('source chips', () => {
  const root = mkdtempSync(join(tmpdir(), 'mama-'));
  mkdirSync(join(root, 'wiki', 'accounts'), { recursive: true });
  writeFileSync(join(root, 'wiki', 'accounts', 'a.md'), 'hello');
  writeFileSync(join(root, '.env'), 'SECRET=1');
  symlinkSync(join(root, '.env'), join(root, 'wiki', 'leak.md'));

  it('reads files in allowed folders', () => {
    expect(readSource(root, 'wiki/accounts/a.md')?.text).toBe('hello');
    expect(readSource(root, '/wiki/accounts/a.md#signals')?.text).toBe('hello');
  });
  it('refuses everything else', () => {
    expect(readSource(root, '.env')).toBeNull();
    expect(readSource(root, 'wiki/../.env')).toBeNull();
    expect(readSource(root, 'wiki/accounts')).toBeNull();
    expect(readSource(root, 'wiki/leak.md')).toBeNull();
  });
});

describe('surface data (dataRef)', () => {
  const root = mkdtempSync(join(tmpdir(), 'mama-'));
  mkdirSync(join(root, 'log', 'weekly'), { recursive: true });
  mkdirSync(join(root, 'knowledge'), { recursive: true });
  writeFileSync(join(root, 'log', 'weekly', '2026-W45.json'), '{"week":"2026-W45"}');
  writeFileSync(join(root, 'log', 'weekly', 'bad.json'), '{nope');
  writeFileSync(join(root, 'knowledge', 'secret.json'), '{"x":1}');
  writeFileSync(join(root, '.env.json'), '{"SECRET":1}');
  symlinkSync(join(root, '.env.json'), join(root, 'log', 'weekly', 'leak.json'));

  it('reads script JSON inside the data folders', () => {
    expect(readData(root, 'log/weekly/2026-W45.json')).toEqual({ ok: true, value: { week: '2026-W45' } });
  });
  it('refuses other folders, non-JSON, traversal and symlinks out', () => {
    for (const p of ['knowledge/secret.json', '.env.json', 'log/../.env.json', 'log/weekly/leak.json', 'wiki/accounts/a.md', 'log/weekly/missing.json']) {
      expect(readData(root, p).ok, p).toBe(false);
    }
  });
  it('reports invalid JSON instead of throwing', () => {
    const r = readData(root, 'log/weekly/bad.json');
    expect(r.ok).toBe(false);
    expect(!r.ok && r.status).toBe(422);
  });
});
