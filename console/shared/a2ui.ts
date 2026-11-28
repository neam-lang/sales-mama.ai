// ```a2ui blocks: split them out of the agent's text, validate them against the Sales Mama catalog,
// make them safe (no send actions, ADR-0006/0007) and expand them to A2UI v0.9 messages.
// Old ```mama-card blocks still render: legacy.ts wraps each in a one-component surface. ADR-0009.
//
// A block is either the compact form agents write:
//   {"surfaceId": "weekly_w46", "title": "…", "agent": "mama", "dataRef": "log/weekly/2026-W46.json",
//    "data": {…local UI state…}, "refs": ["…"], "components": [{"id": "root", …}, …]}
// or raw protocol messages: {"surfaceId": "…", "dataRef": "…", "messages": [{"version": "v0.9", …}]}.
// The console loads dataRef (read-only, allow-listed) into the data model at "/"; `data` goes to "/ui".
import { basicCatalog } from '@a2ui/web_core/v0_9/basic_catalog';
import { API, CARDS, CARD_FIELD_RENAMES, CARD_FOR_TYPE, CATALOG_ID, DATA_PROPS, PROTOCOL, type CardName, type ComponentName } from './a2ui-api';
import { parseCard, validateCard } from './cards';

export interface A2uiComponent { id: string; component: string; [k: string]: unknown }
export interface SurfaceBlock {
  surfaceId: string;
  title?: string;
  subtitle?: string;
  agent?: string;
  dataRef?: string;
  data?: Record<string, unknown>;
  refs?: string[];
  components: A2uiComponent[];
  extra: Record<string, unknown>[];   // raw messages other than createSurface/updateComponents
  legacy?: boolean;
}

export type Part =
  | { kind: 'md'; text: string }
  | { kind: 'surface'; block: SurfaceBlock; issues: string[] }
  | { kind: 'bad'; raw: string; issues: string[] }
  | { kind: 'pending' };

/** Folders a dataRef may point into (the server enforces the same list, plus symlink checks). */
export const DATA_PREFIXES = ['log/', 'wiki/books/', 'company-check/reports/', 'company-check/leads/'];
export const MAX_ACTIONS = 4;
const SEND = /\bsend\b/i;
const ID = /^[A-Za-z_][A-Za-z0-9_]*$/;
const COMMON_KEYS = new Set(['id', 'component', 'weight', 'accessibility', 'checks']);

const FENCE = /```(a2ui|mama-card)[^\n]*\n([\s\S]*?)```/g;
const OPEN = /```(a2ui|mama-card)/;
const PARTIAL = /`{1,3}(a(2(u(i)?)?)?|m(a(m(a(-(c(a(r(d)?)?)?)?)?)?)?)?)?$/;

/** Split agent text into markdown and surface parts, in order. Unclosed fences become `pending`. */
export function splitParts(text: string): Part[] {
  const parts: Part[] = [];
  let last = 0, n = 0;
  for (const m of text.matchAll(FENCE)) {
    pushMd(parts, text.slice(last, m.index));
    parts.push(m[1] === 'a2ui' ? parseBlock(m[2]) : legacyPart(m[2], n));
    n += 1;
    last = m.index! + m[0].length;
  }
  const tail = text.slice(last);
  const open = OPEN.exec(tail);
  if (open) {
    pushMd(parts, tail.slice(0, open.index));
    parts.push({ kind: 'pending' });
  } else {
    pushMd(parts, tail.replace(PARTIAL, ''));
  }
  return parts;
}

export function surfacesIn(text: string) {
  return splitParts(text).filter((p): p is Extract<Part, { kind: 'surface' | 'bad' }> => p.kind === 'surface' || p.kind === 'bad');
}

function pushMd(parts: Part[], text: string) {
  if (text.trim()) parts.push({ kind: 'md', text });
}

/** A mama-card from an old recording or saved result becomes a one-component surface: operational types
 *  map to their *Card component, retired report types (book, chart, …) to LegacyCard. */
function legacyPart(raw: string, n: number): Part {
  const p = parseCard(raw);
  if (p.kind !== 'card') return p.kind === 'bad' ? { kind: 'bad', raw: p.raw, issues: p.issues } : { kind: 'pending' };
  const { type, ...fields } = p.card;
  const name = CARD_FOR_TYPE[String(type)];
  const block: SurfaceBlock = {
    surfaceId: `legacy_${n}_${String(type).replace(/\W/g, '_')}`, legacy: true, extra: [],
    components: [name ? { id: 'root', component: name, ...toCardProps(fields) } : { id: 'root', component: 'LegacyCard', card: p.card, issues: p.issues }],
  };
  return { kind: 'surface', block, issues: name ? p.issues : [] };
}

/** Card fields ⇄ component props (only `checks` ⇄ `passed` differ). */
export function toCardProps(fields: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(fields).map(([k, v]) => [CARD_FIELD_RENAMES[k] ?? k, v]));
}
export function fromCardProps(props: Record<string, unknown>) {
  const back = Object.fromEntries(Object.entries(CARD_FIELD_RENAMES).map(([a, b]) => [b, a]));
  return Object.fromEntries(Object.entries(props).map(([k, v]) => [back[k] ?? k, v]));
}

/** A surface that is only operational cards (no title, data or refs) renders without the report frame. */
export function isBare(b: SurfaceBlock): boolean {
  if (b.legacy) return true;
  if (b.title || b.subtitle || b.dataRef || b.refs?.length) return false;
  const nonLayout = b.components.filter(c => !['Column', 'Row'].includes(c.component));
  return nonLayout.length > 0 && nonLayout.every(c => c.component in CARDS);
}

export function parseBlock(raw: string): Part {
  let value: any;
  try { value = JSON.parse(raw); } catch (err) {
    return { kind: 'bad', raw, issues: [`not valid JSON: ${(err as Error).message}`] };
  }
  if (Array.isArray(value)) value = { messages: value };
  if (!value || typeof value !== 'object') return { kind: 'bad', raw, issues: ['an a2ui block is a JSON object'] };
  const issues: string[] = [];
  const block = normalise(value, issues);
  if (!block) return { kind: 'bad', raw, issues };
  issues.push(...repairAliases(block));
  issues.push(...validateBlock(block));
  issues.push(...pruneInvalid(block));
  return { kind: 'surface', block, issues };
}

/** Field names models often use for a component's list (seen in live runs): fixed before validation. */
const ALIASES: Record<string, Record<string, string>> = {
  ActionBar: { items: 'actions', buttons: 'actions', prompts: 'actions' },
};
function repairAliases(b: SurfaceBlock): string[] {
  const out: string[] = [];
  for (const c of b.components) {
    const map = c && ALIASES[c.component as string];
    if (!map) continue;
    for (const [from, to] of Object.entries(map)) {
      if (c[from] !== undefined && c[to] === undefined) { c[to] = c[from]; delete c[from]; out.push(`${c.id} (${c.component}): read "${from}" as "${to}"`); }
    }
  }
  return out;
}

/** Props to check against the catalog. An ActionBar may bind its list to the report data
 *  ({"path": "/sections/leads/next"}): it is resolved, filtered and capped in toMessages. */
function propsForSchema(c: A2uiComponent): Record<string, unknown> {
  const props = Object.fromEntries(Object.entries(c).filter(([k]) => !COMMON_KEYS.has(k)));
  if (c.component === 'ActionBar' && isBinding(props.actions)) props.actions = [];
  return props;
}

function schemaOk(c: A2uiComponent): boolean {
  const ours = (API as Record<string, { schema: any }>)[c.component];
  const basic = basicCatalog.components.get(c.component) as { schema: any } | undefined;
  if (!ours && !basic) return false;
  const schema = ours ? (typeof ours.schema.strict === 'function' ? ours.schema.strict() : ours.schema) : basic!.schema;
  return schema.safeParse(propsForSchema(c)).success;
}

/**
 * Best effort for generated views: a component the catalog rejects is left out (with every reference
 * to it), so one slip never blanks the whole report ("[Loading root...]"). The root is always kept.
 */
export function pruneInvalid(b: SurfaceBlock): string[] {
  const valid = b.components.filter(c => c && typeof c.id === 'string' && typeof c.component === 'string');
  const bad = new Set(valid.filter(c => c.id !== 'root' && !schemaOk(c)).map(c => c.id));
  const ids = new Set(valid.map(c => c.id).filter(id => !bad.has(id)));
  if (!bad.size && valid.every(c => childRefs(c).every(r => ids.has(r)))) return [];
  b.components = valid.filter(c => !bad.has(c.id));
  for (const c of b.components) {
    if (Array.isArray(c.children)) c.children = c.children.filter((x: unknown) => typeof x !== 'string' || ids.has(x));
    if (typeof c.child === 'string' && !ids.has(c.child)) delete c.child;
  }
  return [...bad].map(id => `${id}: left out so the rest of the view shows`);
}

function normalise(v: any, issues: string[]): SurfaceBlock | null {
  let surfaceId = typeof v.surfaceId === 'string' ? v.surfaceId : '';
  let components: A2uiComponent[] = Array.isArray(v.components) ? v.components : [];
  const extra: Record<string, unknown>[] = [];
  if (Array.isArray(v.messages)) {
    for (const m of v.messages) {
      if (!m || typeof m !== 'object') { issues.push('a message is not an object'); continue; }
      if (m.version && m.version !== PROTOCOL) issues.push(`message version ${m.version}; this console speaks ${PROTOCOL}`);
      if (m.createSurface) surfaceId ||= String(m.createSurface.surfaceId ?? '');
      else if (m.updateComponents) components = components.concat(m.updateComponents.components ?? []);
      else if (m.updateDataModel) extra.push({ updateDataModel: m.updateDataModel });
      else if (m.deleteSurface) continue;
      else issues.push(`unknown message: ${Object.keys(m).join(', ')}`);
    }
  }
  if (!surfaceId) { issues.push('a surface needs "surfaceId"'); return null; }
  if (!components.length) { issues.push('a surface needs "components" with a "root"'); return null; }
  const str = (x: unknown) => (typeof x === 'string' ? x : undefined);
  return {
    surfaceId, components, extra, title: str(v.title), subtitle: str(v.subtitle), agent: str(v.agent),
    dataRef: str(v.dataRef),
    data: v.data && typeof v.data === 'object' && !Array.isArray(v.data) ? v.data : undefined,
    refs: Array.isArray(v.refs) ? v.refs.filter((r: unknown) => typeof r === 'string') : undefined,
  };
}

const isBinding = (x: unknown) => !!x && typeof x === 'object' && !Array.isArray(x)
  && (typeof (x as any).path === 'string' || typeof (x as any).call === 'string');

/** Check a block against the catalog; strip send actions in place. Returns human-readable issues. */
export function validateBlock(b: SurfaceBlock): string[] {
  const issues: string[] = [];
  if (!ID.test(b.surfaceId)) issues.push(`surfaceId "${b.surfaceId}" should be letters, digits and _`);
  if (b.dataRef !== undefined && !dataRefAllowed(b.dataRef)) {
    issues.push(`dataRef "${b.dataRef}" must be a .json file under ${DATA_PREFIXES.join(', ')}`);
  }
  const ids = new Map<string, A2uiComponent>();
  for (const c of b.components) {
    if (!c || typeof c.id !== 'string' || typeof c.component !== 'string') { issues.push('a component needs "id" and "component"'); continue; }
    if (ids.has(c.id)) issues.push(`duplicate component id "${c.id}"`);
    ids.set(c.id, c);
  }
  if (!ids.has('root')) issues.push('no component with id "root"');
  let actions = 0;
  for (const c of ids.values()) {
    const where = `${c.id} (${c.component})`;
    const ours = (API as Record<string, { schema: any }>)[c.component];
    const basic = basicCatalog.components.get(c.component) as { schema: any } | undefined;
    if (!ours && !basic) { issues.push(`${where}: not in the Sales Mama catalog`); continue; }
    const props = propsForSchema(c);
    const schema = ours ? (typeof ours.schema.strict === 'function' ? ours.schema.strict() : ours.schema) : basic!.schema;
    const res = schema.safeParse(props);
    if (!res.success) {
      for (const i of res.error.issues.slice(0, 4)) issues.push(`${where}: ${i.path.join('.') || '(props)'} ${i.message}`);
    }
    for (const ref of childRefs(c)) if (!ids.has(ref)) issues.push(`${where}: child "${ref}" does not exist`);
    if (b.dataRef && !b.legacy) {
      for (const key of DATA_PROPS[c.component as ComponentName] ?? []) {
        if (c[key] !== undefined && !isBinding(c[key])) issues.push(`${where}: "${key}" is typed in; bind it to the data with {"path": …}`);
      }
    }
    if (c.component in CARDS && !Object.values(c).some(isBinding)) {
      const { id: _id, component: _c, ...fields } = c;
      for (const i of validateCard({ ...fromCardProps(fields), type: CARDS[c.component as CardName].type })) {
        issues.push(`${where}: ${i.replace(/\/checks\b/, '/passed').replace(/^\/id\b|^\(card\) must have required property 'id'/, m => m.replace('id', 'account_id'))}`);
      }
    }
    if ((c.component === 'ActionBar' || c.component in CARDS) && Array.isArray(c.actions)) {
      const before = c.actions.length;
      c.actions = c.actions.filter((a: any) => a && !SEND.test(String(a.label)) && !SEND.test(String(a.prompt)))
        .slice(0, Math.max(0, MAX_ACTIONS - actions));
      actions += (c.actions as unknown[]).length;
      if ((c.actions as unknown[]).length < before) issues.push(`${where}: dropped ${before - (c.actions as unknown[]).length} action(s) (send, or more than ${MAX_ACTIONS})`);
    }
    if (c.component === 'Button' && c.action && typeof c.action === 'object') {
      const ev = (c.action as any).event;
      const prompt = String(ev?.context?.prompt ?? '');
      if (!ev || SEND.test(String(ev.name)) || SEND.test(prompt) || actions >= MAX_ACTIONS) {
        delete c.action;
        issues.push(`${where}: action removed (only "prompt"/"open" events, never send, at most ${MAX_ACTIONS})`);
      } else if (ev.name === 'prompt') actions += 1;
    }
  }
  return issues;
}

function childRefs(c: A2uiComponent): string[] {
  const out: string[] = [];
  if (typeof c.child === 'string') out.push(c.child);
  if (Array.isArray(c.children)) out.push(...c.children.filter((x): x is string => typeof x === 'string'));
  else if (c.children && typeof c.children === 'object' && typeof (c.children as any).componentId === 'string') {
    out.push((c.children as any).componentId);
  }
  if (Array.isArray(c.tabs)) for (const t of c.tabs as any[]) if (typeof t?.child === 'string') out.push(t.child);
  if (typeof c.trigger === 'string') out.push(c.trigger);
  if (typeof c.content === 'string' && c.component === 'Modal') out.push(c.content);
  return out;
}

export function dataRefAllowed(p: string): boolean {
  return p.endsWith('.json') && !p.split('/').includes('..') && !p.startsWith('/') && DATA_PREFIXES.some(x => p.startsWith(x));
}

/** The v0.9 message list for a block, with the dataRef content (if any) as the initial data model. */
export function toMessages(b: SurfaceBlock, refData?: unknown): Record<string, unknown>[] {
  const v = PROTOCOL;
  const model: Record<string, unknown> = refData && typeof refData === 'object' && !Array.isArray(refData)
    ? { ...(refData as Record<string, unknown>) } : refData !== undefined ? { value: refData } : {};
  if (b.data) model.ui = b.data;
  return [
    { version: v, createSurface: { surfaceId: b.surfaceId, catalogId: CATALOG_ID } },
    { version: v, updateDataModel: { surfaceId: b.surfaceId, path: '/', value: model } },
    ...b.extra.map(m => ({ version: v, ...m, ...(m.updateDataModel ? { updateDataModel: { ...(m.updateDataModel as object), surfaceId: b.surfaceId } } : {}) })),
    { version: v, updateComponents: { surfaceId: b.surfaceId, components: b.components.map(c => resolveActions(c, model)) } },
  ];
}

/** A bound ActionBar list from the report data: label + prompt only, never send, at most MAX_ACTIONS. */
function resolveActions(c: A2uiComponent, model: unknown): A2uiComponent {
  if (c.component !== 'ActionBar' || !isBinding(c.actions)) return c;
  const list = at(model, String((c.actions as { path?: string }).path ?? ''));
  const actions = (Array.isArray(list) ? list : [])
    .filter((a: any) => a && typeof a.label === 'string' && typeof a.prompt === 'string' && !SEND.test(a.label) && !SEND.test(a.prompt))
    .slice(0, MAX_ACTIONS).map((a: any) => ({ label: a.label, prompt: a.prompt }));
  return { ...c, actions };
}

/** Resolve a JSON-pointer-ish path ("/a/b/0") in plain data. Used by tests and the exporter. */
export function at(data: unknown, path: string): unknown {
  let cur: any = data;
  for (const seg of path.split('/').filter(Boolean)) {
    if (cur == null) return undefined;
    cur = cur[decodeURIComponent(seg.replace(/~1/g, '/').replace(/~0/g, '~'))];
  }
  return cur;
}
