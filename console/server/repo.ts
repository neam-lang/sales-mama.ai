// Read-only access to the repo: who the user is, the bento rail, and source chips.
import { execFileSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync, realpathSync, statSync } from 'node:fs';
import { join, normalize, resolve, sep } from 'node:path';
import { parse as parseYaml } from 'yaml';
import { parseBook, parseTeam } from '../shared/book';
import { sendWindow, type MarketWindow } from '../shared/window';
import type { Me, Rail } from '../shared/protocol';

/** Folders a source chip may open. Everything else (e.g. .env, .git) is refused. */
const READABLE = ['wiki/', 'raw/', 'knowledge/', 'log/', 'reps/', 'templates/', 'docs/',
  'company-check/reports/', 'company-check/evidence/', 'company-check/leads/', 'company-check/README.md']; // never company-check/data/
const MAX_BYTES = 256 * 1024;

export function findRepoRoot(start: string): string {
  let dir = resolve(start);
  for (;;) {
    if (existsSync(join(dir, 'AGENTS.md')) && existsSync(join(dir, 'knowledge'))) return dir;
    const up = resolve(dir, '..');
    if (up === dir) throw new Error(`Not inside the Sales Mama repo: ${start}`);
    dir = up;
  }
}

function frontmatter(text: string): Record<string, any> {
  const m = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text);
  if (!m) return {};
  try { return parseYaml(m[1]) ?? {}; } catch { return {}; }
}

export function currentUser(root: string): { email: string; me: Me | null } {
  let email = process.env.MAMA_USER_EMAIL ?? '';
  if (!email) {
    try { email = execFileSync('git', ['config', 'user.email'], { cwd: root, encoding: 'utf8' }).trim(); } catch { /* unset */ }
  }
  const dir = join(root, 'reps');
  if (!email || !existsSync(dir)) return { email, me: null };
  for (const f of readdirSync(dir).filter(f => f.endsWith('.md'))) {
    const meta = frontmatter(readFileSync(join(dir, f), 'utf8'));
    if (String(meta.email ?? '').toLowerCase() === email.toLowerCase()) {
      return {
        email,
        me: {
          id: String(meta.id ?? f.replace(/\.md$/, '')), name: String(meta.name ?? ''), email,
          role: String(meta.role ?? 'rep'), markets: (meta.markets ?? []).map(String),
        },
      };
    }
  }
  return { email, me: null };
}

export function readRail(root: string, now = new Date()): Rail {
  const { email, me } = currentUser(root);
  if (!me) {
    return {
      me: null, book: null, team: null, windows: [], bookPath: null,
      problem: email ? `No rep profile for ${email}. Run /mama-setup.` : 'git user.email is not set. Run /mama-setup.',
    };
  }
  const bookPath = `wiki/books/${me.id}.md`;
  const read = (p: string) => (existsSync(join(root, p)) ? readFileSync(join(root, p), 'utf8') : null);
  const bookMd = read(bookPath);
  const teamMd = me.role === 'manager' ? read('wiki/books/team.md') : null;
  let windows: Rail['windows'] = [];
  try {
    const markets = parseYaml(read('knowledge/markets.yaml') ?? '')?.markets ?? {};
    windows = me.markets.filter(m => markets[m]).map(m => sendWindow(m, markets[m] as MarketWindow, now));
  } catch { /* leave the tile out */ }
  return {
    me, bookPath, windows,
    book: bookMd ? parseBook(bookMd) : null,
    team: teamMd ? parseTeam(teamMd) : null,
    problem: bookMd ? undefined : `${bookPath} isn't built yet. It appears after the next session start or sync.`,
  };
}

/** Read one repo file for a source chip. Returns null when the path is not allowed. */
export function readSource(root: string, rel: string): { path: string; text: string; truncated: boolean } | null {
  const clean = normalize(rel.replace(/\\/g, '/').replace(/^\/+/, '').replace(/#.*$/, '')).split(sep).join('/');
  if (clean.split('/').includes('..') || !READABLE.some(p => clean.startsWith(p))) return null;
  const full = resolve(root, clean);
  if (!existsSync(full)) return null;
  const real = realpathSync(full);
  const realRoot = realpathSync(root) + sep;
  // A symlink must land inside an allowed folder too (e.g. not wiki/x.md → .env).
  if (!real.startsWith(realRoot) || !READABLE.some(p => real.slice(realRoot.length).split(sep).join('/').startsWith(p))) return null;
  const st = statSync(real);
  if (!st.isFile()) return null;
  const buf = readFileSync(real);
  return { path: clean, text: buf.subarray(0, MAX_BYTES).toString('utf8'), truncated: buf.length > MAX_BYTES };
}
