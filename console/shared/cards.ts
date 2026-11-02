// mama-card blocks: split them out of the agent's text and validate them against
// console/cards.schema.json (docs/UI.md §2).
import Ajv2020 from 'ajv/dist/2020.js';
import schema from '../cards.schema.json';

export interface CardAction { label: string; prompt: string; style?: 'primary' | 'secondary' }
export interface Card {
  type: string;
  title: string;
  subtitle?: string;
  agent?: string;
  refs?: string[];
  actions?: CardAction[];
  [k: string]: unknown;
}

export type Part =
  | { kind: 'md'; text: string }
  | { kind: 'card'; card: Card; issues: string[] }   // issues empty = valid
  | { kind: 'bad'; raw: string; issues: string[] }    // not JSON, or no type/title
  | { kind: 'pending' };                              // fence still streaming

const ajv = new Ajv2020({ allErrors: true, strict: false });
const check = ajv.compile(schema);

export function validateCard(value: unknown): string[] {
  if (check(value)) return [];
  const seen = new Set<string>();
  for (const err of check.errors ?? []) {
    if (err.keyword === 'if') continue; // the "then" failure underneath says what is wrong
    const where = err.instancePath || '(card)';
    const extra = err.keyword === 'enum' ? ` (${(err.params as any).allowedValues.join(', ')})` : '';
    seen.add(`${where} ${err.message}${extra}`);
  }
  return [...seen];
}

const FENCE = /```mama-card[^\n]*\n([\s\S]*?)```/g;
const OPEN = /```mama-card/;

/** Split agent text into markdown and card parts, in order. Unclosed fences become `pending`. */
export function splitCards(text: string): Part[] {
  const parts: Part[] = [];
  let last = 0;
  for (const m of text.matchAll(FENCE)) {
    pushMd(parts, text.slice(last, m.index));
    parts.push(parseCard(m[1]));
    last = m.index! + m[0].length;
  }
  const tail = text.slice(last);
  const open = OPEN.exec(tail);
  if (open) {
    pushMd(parts, tail.slice(0, open.index));
    parts.push({ kind: 'pending' });
  } else {
    // Hide a fence that is only partly typed ("``", "```mama-c").
    pushMd(parts, tail.replace(/`{1,3}(m(a(m(a(-(c(a(r(d)?)?)?)?)?)?)?)?)?$/, ''));
  }
  return parts;
}

export function parseCard(raw: string): Part {
  let value: unknown;
  try { value = JSON.parse(raw); } catch (err) {
    return { kind: 'bad', raw, issues: [`not valid JSON: ${(err as Error).message}`] };
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || typeof (value as Card).type !== 'string' || typeof (value as Card).title !== 'string') {
    return { kind: 'bad', raw, issues: ['a card needs at least "type" and "title"'] };
  }
  const card = value as Card;
  card.actions = safeActions(card.actions);
  return { kind: 'card', card, issues: validateCard(value) };
}

/** ADR-0006: the console never offers a send button, whatever a card asks for. */
export function safeActions(actions: unknown): CardAction[] {
  if (!Array.isArray(actions)) return [];
  return actions
    .filter((a): a is CardAction => !!a && typeof a.label === 'string' && typeof a.prompt === 'string')
    .filter(a => !/\bsend\b/i.test(a.label))
    .slice(0, 4);
}

export function cardsIn(text: string): Extract<Part, { kind: 'card' | 'bad' }>[] {
  return splitCards(text).filter((p): p is Extract<Part, { kind: 'card' | 'bad' }> => p.kind === 'card' || p.kind === 'bad');
}

function pushMd(parts: Part[], text: string) {
  if (text.trim()) parts.push({ kind: 'md', text });
}
