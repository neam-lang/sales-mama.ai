// The "ear" layer (voice spec §6): turns an answer written for the eye into a short line for the ear.
// Pure and DOM-free so the server, the browser and the tests share it.
// - V1–V3 speak only the answer's lead line (AGENTS.md: a skill ends with a one-line summary).
// - Paths, URLs, code, tables and emoji are never spoken; instruction-shaped sentences from
//   untrusted text are dropped and reported (AGENTS.md rule 15).
import type { Item, TextItem, Turn } from './stream';

export const MAX_WORDS = 60;
export const MAX_WORDS_BRIEF = 120;

const REPO_PATH = /(?:^|[\s(])(?:\.{0,2}\/)?(?:wiki|raw|knowledge|log|reps|scripts|templates|docs|company-check|console|evals|runner|benchmark)\/[^\s),;]*/g;
const URL = /\bhttps?:\/\/[^\s)]+|\bwww\.[^\s)]+/gi;
const EMAIL = /\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b/g;
const EMOJI = /[\p{Extended_Pictographic}\u{1F1E6}-\u{1F1FF}\u{FE0F}\u{200D}]/gu;
/** Text that tries to steer the assistant. It may come from raw/ content quoted in an answer. */
const INSTRUCTION = /\b(ignore (?:all |any |the )?(?:previous|prior|above|earlier)|disregard (?:the|all|any|previous)|forward (?:this|it|all|them|the)|send (?:it|this|them|all|everything) to|add me to|system prompt|you must now|new instructions|reveal (?:your|the) (?:prompt|rules))\b/i;

const MARKETS: Record<string, string> = { SG: 'Singapore', MY: 'Malaysia', IN: 'India' };
const STEPS: Record<string, string> = { fu1: 'first follow-up', fu2: 'second follow-up', fu3: 'third follow-up' };

/** "14:00" or "2026-11-18T14:00:00+08:00" → "2 pm"; "09:30" → "9:30 am". */
export function spokenTime(h: number, m: number): string {
  const ap = h < 12 ? 'am' : 'pm';
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return m ? `${h12}:${String(m).padStart(2, '0')} ${ap}` : `${h12} ${ap}`;
}

/** The answer: text after the last tool call (the same split the chat view uses). */
export function answerText(items: Item[]): string {
  let lastTool = -1;
  items.forEach((it, i) => { if (it.kind === 'tool') lastTool = i; });
  return items.filter((it, i): it is TextItem => it.kind === 'text' && i > lastTool && !!it.text.trim()).map(t => t.text).join('\n\n');
}

/** The lead: the first paragraph of prose, before any card or surface, skipping headings and tables. */
export function leadOf(markdown: string): string {
  const prose = stripFences(markdown);
  for (const para of prose.split(/\n\s*\n/)) {
    const lines = para.split('\n').map(l => l.trim()).filter(l => l && !/^#{1,6}\s/.test(l) && !/^\|/.test(l) && !/^[-*_]{3,}$/.test(l));
    if (lines.length) return lines.join(' ');
  }
  return '';
}

function stripFences(md: string): string {
  return md.replace(/```[\s\S]*?(```|$)/g, '\n\n').replace(/~~~[\s\S]*?(~~~|$)/g, '\n\n');
}

export interface Spoken { text: string; dropped: string[]; words: number }

/** Markdown → plain spoken text, capped at a sentence boundary. */
export function speakable(md: string, maxWords = MAX_WORDS): Spoken {
  let t = stripFences(md);
  t = t.replace(/^\s*\|.*\|\s*$/gm, ' ');                          // table rows
  t = t.replace(/!\[[^\]]*\]\([^)]*\)/g, ' ');                       // images
  t = t.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1');                     // links → their text
  t = t.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_, a: string, b?: string) => b ?? a.split('/').pop()!.replace(/-/g, ' ')); // wiki links
  t = t.replace(/`[^`]*`/g, ' ');                                     // inline code: commands, paths, ids
  t = t.replace(URL, ' ').replace(EMAIL, ' ').replace(REPO_PATH, ' ');
  t = t.replace(/^\s{0,3}(?:#{1,6}|>|[-*+]|\d+[.)])\s+/gm, '');      // headings, quotes, list markers
  t = t.replace(/(\*\*|__|\*|_|~~)(?=\S)([^*_~]+?)\1/g, '$2');        // emphasis
  t = t.replace(EMOJI, '');
  t = t.replace(/\b(?:\d{4}-\d{2}-\d{2}T)?([01]?\d|2[0-3]):([0-5]\d)(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?\b/g, (_, h, m) => spokenTime(+h, +m));
  t = t.replace(/\b(SG|MY|IN)\b/g, (c: string) => MARKETS[c]);
  t = t.replace(/\b(fu[123])\b/g, (s: string) => STEPS[s]);
  t = t.replace(/\btier ([ABC])\b/gi, 'tier $1');
  t = t.replace(/\s*[·•|]\s*/g, ', ').replace(/\s*[—–]\s*/g, ', ');
  t = t.replace(/\s+/g, ' ').replace(/\s+([,.;:!?])/g, '$1').replace(/([,;:])(?:\s*[,;:])+/g, '$1').trim();
  t = t.replace(/^[,;:\s]+/, '');

  const dropped: string[] = [];
  const out: string[] = [];
  let words = 0;
  for (const raw of sentences(t)) {
    const s = raw.trim();
    if (!s) continue;
    if (INSTRUCTION.test(s)) { dropped.push(s); continue; }
    const n = s.split(/\s+/).length;
    if (words + n > maxWords) {
      if (out.length === 0) {                                          // one very long sentence: cut at a word
        out.push(s.split(/\s+/).slice(0, maxWords).join(' ').replace(/[,;:]$/, '') + '.');
        words = maxWords;
      }
      break;
    }
    out.push(s);
    words += n;
  }
  const text = out.join(' ').replace(/([^.!?])$/, '$1.');
  return { text: text === '.' ? '' : text, dropped, words };
}

function sentences(t: string): string[] {
  // Split after . ! ? followed by a space and a capital or digit; keep "S$12.40" and "e.g." together.
  return t.split(/(?<=[.!?])\s+(?=[A-Z0-9"'(])/);
}

/** What to say when a turn ends (V1–V3): the lead line, plus approvals and errors. */
export function spokenAnswer(turn: Turn, error?: { message: string; fix?: string }): Spoken {
  if (error) return speakable(`${error.message} ${error.fix ?? ''}`, 30);
  const lead = speakable(leadOf(answerText(turn.items)));
  const denied = turn.denied.length;
  if (!denied) return lead;
  const extra = `${denied === 1 ? 'One step needs' : `${denied} steps need`} your approval in Claude Code.`;
  return { ...lead, text: `${lead.text} ${extra}`.trim(), words: lead.words + extra.split(' ').length };
}

/**
 * Live mode (spec §18): the next complete, speakable part of an answer that is still streaming.
 * `from` is how much of `text` was already consumed. Card and surface fences are skipped once
 * closed (and waited for while open); only complete sentences or lines are spoken until `final`.
 */
export function streamChunk(text: string, from: number, final: boolean): { say: string; next: number } {
  let i = from, out = '';
  while (i < text.length) {
    const fence = text.indexOf('```', i);
    const stop = fence === -1 ? text.length : fence;
    const seg = text.slice(i, stop);
    // Up to the last sentence end or line break in this segment (all of it if the fence or the end follows).
    let cut = seg.length;
    if (fence === -1 && !final) {
      const m = [...seg.matchAll(/[.!?](?=\s)|\n/g)].pop();
      cut = m ? m.index! + 1 : 0;
    }
    out += seg.slice(0, cut);
    i += cut;
    if (cut < seg.length || fence === -1) break;          // waiting for more text
    const close = text.indexOf('```', fence + 3);
    if (close === -1) break;                               // a card is still streaming: wait for it
    i = close + 3;
    out += '\n';
  }
  // A line without end punctuation (a list item, a heading) ends a sentence when spoken.
  const lined = out.split('\n').map(l => l.trim()).filter(Boolean).map(l => (/[.!?:;,]$/.test(l) || /^\|/.test(l) ? l : `${l}.`)).join('\n');
  return { say: speakable(lined, 400).text, next: i };
}
