// Spoken account names → account ids (voice spec §4, §5.2). Pure and tested.
// Only the accounts the console already lists for @-mentions are candidates, so a rep can never
// resolve to another rep's account (AGENTS.md rule 16). Nothing is guessed: below 0.9 the
// read-back pauses and asks the user to pick (as rule 10 does for signals).

export interface Candidate { id: string; name: string }
export interface Mention { said: string; id: string; name: string; conf: number; start: number; end: number; alternatives: Candidate[] }

export const SURE = 0.9;
export const MAYBE = 0.78;

const SUFFIX = /\b(pte|pvt|private|sdn|bhd|berhad|ltd|limited|llp|inc|co|company|corp|corporation|plc|the)\b\.?/g;

export function normalise(s: string): string {
  return s.toLowerCase().replace(/&/g, ' and ').replace(/[^\p{L}\p{N}\s-]/gu, ' ').replace(/-/g, ' ')
    .replace(SUFFIX, ' ').replace(/\s+/g, ' ').trim();
}

/** A rough phonetic key: drops vowels after the first letter and folds sound-alike consonants. */
export function phonetic(s: string): string {
  return normalise(s).split(' ').map(w => {
    const k = w.replace(/ph/g, 'f').replace(/ck|q/g, 'k').replace(/c(?=[eiy])/g, 's').replace(/c/g, 'k')
      .replace(/z/g, 's').replace(/x/g, 'ks').replace(/wh/g, 'w').replace(/(.)\1+/g, '$1');
    return k[0] + k.slice(1).replace(/[aeiouhwy]/g, '');
  }).join(' ');
}

export function jaroWinkler(a: string, b: string): number {
  if (a === b) return 1;
  if (!a.length || !b.length) return 0;
  const range = Math.max(0, Math.floor(Math.max(a.length, b.length) / 2) - 1);
  const am = new Array(a.length).fill(false), bm = new Array(b.length).fill(false);
  let matches = 0;
  for (let i = 0; i < a.length; i++) {
    for (let j = Math.max(0, i - range); j < Math.min(b.length, i + range + 1); j++) {
      if (bm[j] || a[i] !== b[j]) continue;
      am[i] = bm[j] = true; matches++; break;
    }
  }
  if (!matches) return 0;
  let t = 0, k = 0;
  for (let i = 0; i < a.length; i++) {
    if (!am[i]) continue;
    while (!bm[k]) k++;
    if (a[i] !== b[k]) t++;
    k++;
  }
  const jaro = (matches / a.length + matches / b.length + (matches - t / 2) / matches) / 3;
  let p = 0;
  while (p < 4 && a[p] === b[p]) p++;
  return jaro + p * 0.1 * (1 - jaro);
}

/** Everyday and command words: a spoken span may not start or end with one (unless it is the exact name). */
const STOP = new Set(('a an the me my i you your we our us on in at of for to from with and or but is are was be it this that these those ' +
  'brief draft check research show open find tell what who how when where which new about before after today tomorrow ' +
  'meeting meetings call calls follow up email emails reply replies please can could would give get send account accounts ' +
  'company companies lead leads deal deals next last first second third day week book do does did have has had any some all').split(' '));

function tokenScore(a: string, b: string): number {
  return Math.max(jaroWinkler(a, b), jaroWinkler(phonetic(a), phonetic(b)) * 0.97);
}

/** Spoken span vs account name. Exact (normalised) names score 1. Otherwise words must line up one to
 *  one (each at least 0.8 alike), or, for a compound split or joined by STT ("blue fin" / "bluefin"),
 *  the names must match closely with spaces removed. */
function similarity(said: string, name: string): number {
  const a = normalise(said), b = normalise(name);
  if (!a || !b) return 0;
  if (a === b) return 1;
  const at = a.split(' '), bt = b.split(' ');
  if (STOP.has(at[0]) || STOP.has(at[at.length - 1])) return 0;
  if (at.length === bt.length) {
    const scores = at.map((w, i) => tokenScore(w, bt[i]));
    if (Math.min(...scores) < 0.8) return 0;
    return scores.reduce((x, y) => x + y, 0) / scores.length;
  }
  const compact = jaroWinkler(a.replace(/ /g, ''), b.replace(/ /g, ''));
  return compact >= 0.92 ? compact : 0;
}

/** Find spoken account names in a transcript. Longest, most confident spans win; spans never overlap. */
export function findMentions(transcript: string, accounts: Candidate[]): Mention[] {
  const tokens = [...transcript.matchAll(/[\p{L}\p{N}'&.-]+/gu)].map(m => ({ w: m[0], start: m.index!, end: m.index! + m[0].length }));
  const names = accounts.map(a => ({ a, label: a.name || a.id.replace(/-/g, ' '), n: normalise(a.name || a.id).split(' ').filter(Boolean).length }))
    .filter(x => x.n > 0);
  const found: Mention[] = [];
  for (let i = 0; i < tokens.length; i++) {
    for (const len of [5, 4, 3, 2, 1]) {
      if (i + len > tokens.length) continue;
      const span = tokens.slice(i, i + len);
      const said = transcript.slice(span[0].start, span[len - 1].end).replace(/[.,!?;:]+$/, '');
      if (normalise(said).length < 3) continue;
      const scored = names.filter(x => Math.abs(x.n - len) <= 1)
        .map(x => ({ x, s: similarity(said, x.label) }))
        .filter(x => x.s > 0)
        .sort((p, q) => q.s - p.s);
      if (!scored.length || scored[0].s < MAYBE) continue;
      const best = scored[0];
      found.push({ said, id: best.x.a.id, name: best.x.label, conf: Math.min(1, +best.s.toFixed(3)), start: span[0].start, end: span[0].start + said.length,
        alternatives: scored.slice(1, 3).filter(s => s.s >= MAYBE - 0.08).map(s => s.x.a) });
    }
  }
  found.sort((p, q) => q.conf - p.conf || (q.end - q.start) - (p.end - p.start));
  const kept: Mention[] = [];
  for (const m of found) if (!kept.some(k => m.start < k.end && k.start < m.end) && !kept.some(k => k.id === m.id)) kept.push(m);
  return kept.sort((p, q) => p.start - q.start);
}

/** The prompt to send: sure mentions become @ids, the way the composer inserts them. */
export function withMentions(transcript: string, mentions: Mention[]): string {
  let out = '', at = 0;
  for (const m of mentions) {
    if (m.conf < SURE) continue;
    out += transcript.slice(at, m.start) + `@${m.id}`;
    at = m.end;
  }
  return (out + transcript.slice(at)).trim();
}

/** Account names as STT custom vocabulary (Inworld `prompts`): allowed characters only, at most 100. */
export function vocabulary(accounts: Candidate[], extra: string[] = []): string[] {
  const clean = (s: string) => s.replace(/[^\p{L}\p{N}\s.,'():!?;-]/gu, ' ').replace(/\s+/g, ' ').trim();
  const out = new Set<string>();
  for (const s of [...extra, ...accounts.map(a => (a.name || a.id.replace(/-/g, ' ')).replace(new RegExp(SUFFIX.source, 'gi'), ' '))]) {
    const c = clean(s);
    if (c.length >= 3) out.add(c);
    if (out.size >= 100) break;
  }
  return [...out];
}
