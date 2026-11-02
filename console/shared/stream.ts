// Turns the `claude -p --output-format stream-json --verbose --include-partial-messages`
// event stream into one chat turn: streaming text, tool chips, agent lanes and a live plan.
// Pure and DOM-free so the browser and the tests share it.

export type ChipStatus = 'running' | 'ok' | 'error' | 'denied';
export type LaneStatus = 'running' | 'done' | 'failed';
export type StepStatus = 'pending' | 'running' | 'done' | 'failed';

export interface TextItem { kind: 'text'; id: string; text: string; done: boolean }
export interface ToolItem { kind: 'tool'; id: string; name: string; input: Record<string, unknown>; status: ChipStatus; note?: string }
export type Item = TextItem | ToolItem;

export interface Lane {
  id: string;           // the Agent/Task tool_use id, i.e. the subagent's parent_tool_use_id
  agent: string;        // subagent_type
  label: string;        // task description
  status: LaneStatus;
  tools: number;        // tool calls the subagent has made
  last: string;         // latest activity, one line
  agentId?: string;     // task id, used by permission_denied events
}

export interface PlanStep { id: string; label: string; status: StepStatus }

export interface TurnResult { ok: boolean; durationMs?: number; costUsd?: number; turns?: number; error?: string }

export interface Turn {
  sessionId?: string;
  items: Item[];
  lanes: Lane[];
  plan: PlanStep[];
  denied: string[];       // permission_denied messages, shown as one "needs approval" card
  hooks: string[];        // hook names that ran (SessionStart etc.)
  result?: TurnResult;
  done: boolean;
}

export type StreamEvent = Record<string, any>;

const AGENT_TOOLS = new Set(['Agent', 'Task']);
const PLAN_TOOLS = new Set(['TodoWrite', 'TaskCreate', 'TaskUpdate']);

export class TurnBuilder {
  turn: Turn = { items: [], lanes: [], plan: [], denied: [], hooks: [], done: false };
  private texts = new Map<string, TextItem>();       // `${messageId}:${index}` → item
  private tools = new Map<string, ToolItem>();
  private lanes = new Map<string, Lane>();
  private streamed = new Set<string>();              // message ids seen as partial stream events
  private blockKeys = new Map<string, string>();     // `${messageId}:${index}` → tool id
  private pendingTasks: PlanStep[] = [];             // TaskCreate calls waiting for their id
  private laneTools = new Map<string, Set<string>>(); // lane id → subagent tool_use ids seen

  apply(e: StreamEvent): void {
    switch (e?.type) {
      case 'system': return this.system(e);
      case 'stream_event': return this.partial(e);
      case 'assistant': return this.assistant(e);
      case 'user': return this.user(e);
      case 'result': return this.result(e);
    }
  }

  applyAll(events: Iterable<StreamEvent>): Turn {
    for (const e of events) this.apply(e);
    return this.turn;
  }

  /** Text the main agent has written so far, all segments joined. */
  text(): string {
    return this.turn.items.filter((i): i is TextItem => i.kind === 'text').map(i => i.text).join('\n\n');
  }

  private system(e: StreamEvent) {
    const sub = e.subtype;
    if (sub === 'init') { this.turn.sessionId = e.session_id; return; }
    if (sub === 'hook_started' && e.hook_name) { this.turn.hooks.push(e.hook_name); return; }
    if (sub === 'permission_denied') {
      const chip = this.tools.get(e.tool_use_id);
      if (chip) { chip.status = 'denied'; chip.note = e.message; }
      const lane = e.agent_id ? this.laneByAgent(e.agent_id) : undefined;
      if (lane) lane.last = `${e.tool_name ?? 'Tool'} needs approval`;
      this.turn.denied.push(`${e.tool_name ?? 'Tool'}: ${String(e.message ?? '').split('\n')[0]}`);
      return;
    }
    if (sub === 'task_started' && e.tool_use_id) {
      this.lane(e.tool_use_id, e.subagent_type, e.description).agentId = e.task_id;
      return;
    }
    if (sub === 'task_progress' && e.tool_use_id) {
      const lane = this.lane(e.tool_use_id, e.subagent_type, undefined);
      if (e.description) lane.last = e.description;
      if (typeof e.usage?.tool_uses === 'number') lane.tools = Math.max(lane.tools, e.usage.tool_uses);
      return;
    }
    if (sub === 'task_notification' && e.tool_use_id) {
      const lane = this.lanes.get(e.tool_use_id);
      if (lane) lane.status = e.status === 'completed' ? 'done' : 'failed';
    }
  }

  private partial(e: StreamEvent) {
    if (e.parent_tool_use_id) return; // subagent token streams only feed lanes via full messages
    const ev = e.event ?? {};
    const msgId: string | undefined = e.api_message_id ?? ev.message?.id;
    if (ev.type === 'message_start' && ev.message?.id) { this.streamed.add(ev.message.id); return; }
    if (!msgId) return;
    this.streamed.add(msgId);
    const key = `${msgId}:${ev.index}`;
    if (ev.type === 'content_block_start') {
      const b = ev.content_block ?? {};
      if (b.type === 'text') this.addText(key, b.text ?? '', false);
      else if (b.type === 'tool_use') { this.blockKeys.set(key, b.id); this.toolUse(b.id, b.name, {}); }
    } else if (ev.type === 'content_block_delta' && ev.delta?.type === 'text_delta') {
      const item = this.texts.get(key) ?? this.addText(key, '', false);
      item.text += ev.delta.text ?? '';
    } else if (ev.type === 'content_block_stop') {
      const item = this.texts.get(key);
      if (item) item.done = true;
    }
  }

  private assistant(e: StreamEvent) {
    const msg = e.message ?? {};
    const content: any[] = Array.isArray(msg.content) ? msg.content : [];
    if (e.parent_tool_use_id) {
      const lane = this.lane(e.parent_tool_use_id, e.subagent_type, e.task_description);
      for (const b of content) {
        if (b.type === 'tool_use') {
          const seen = this.laneTools.get(lane.id) ?? new Set<string>();
          seen.add(b.id);
          this.laneTools.set(lane.id, seen);
          lane.tools = Math.max(lane.tools, seen.size); // task_progress may have counted it already
          lane.last = describeTool(b.name, b.input ?? {});
        }
        else if (b.type === 'text' && b.text?.trim()) lane.last = b.text.trim().split('\n')[0].slice(0, 140);
      }
      return;
    }
    content.forEach((b, i) => {
      if (b.type === 'text' && !this.streamed.has(msg.id)) {
        // Without partial messages each block arrives whole.
        this.addText(`${msg.id}:full:${i}`, b.text ?? '', true);
      } else if (b.type === 'tool_use') {
        this.toolUse(b.id, b.name, b.input ?? {});
      }
    });
  }

  private user(e: StreamEvent) {
    const content: any[] = Array.isArray(e.message?.content) ? e.message.content : [];
    for (const b of content) {
      if (b.type !== 'tool_result') continue;
      const lane = this.lanes.get(b.tool_use_id);
      if (lane && !e.parent_tool_use_id) { lane.status = b.is_error ? 'failed' : 'done'; continue; }
      const chip = this.tools.get(b.tool_use_id);
      if (chip && chip.status !== 'denied') chip.status = b.is_error ? 'error' : 'ok';
      if (chip?.name === 'TaskCreate') this.bindTaskId(resultText(b.content));
    }
  }

  private result(e: StreamEvent) {
    if (e.session_id) this.turn.sessionId = e.session_id;
    const ok = !e.is_error && (e.subtype === 'success' || e.subtype === undefined);
    this.turn.result = {
      ok, durationMs: e.duration_ms, costUsd: e.total_cost_usd, turns: e.num_turns,
      error: ok ? undefined : (Array.isArray(e.errors) && e.errors.length ? e.errors.join('; ') : (e.result || e.subtype || 'The run failed')),
    };
    for (const t of this.texts.values()) t.done = true;
    for (const c of this.tools.values()) if (c.status === 'running') c.status = ok ? 'ok' : 'error';
    for (const l of this.lanes.values()) if (l.status === 'running') l.status = ok ? 'done' : 'failed';
    this.turn.done = true;
  }

  private addText(key: string, text: string, done: boolean): TextItem {
    const item: TextItem = { kind: 'text', id: key, text, done };
    this.texts.set(key, item);
    this.turn.items.push(item);
    return item;
  }

  private toolUse(id: string, name: string, input: Record<string, unknown>) {
    if (AGENT_TOOLS.has(name)) {
      if (Object.keys(input).length) this.lane(id, input.subagent_type as string, input.description as string);
      else this.lane(id, undefined, undefined);
      return;
    }
    if (PLAN_TOOLS.has(name)) this.plan(name, input);
    const existing = this.tools.get(id);
    if (existing) { if (Object.keys(input).length) existing.input = input; return; }
    if (PLAN_TOOLS.has(name)) { this.tools.set(id, { kind: 'tool', id, name, input, status: 'running' }); return; } // tracked, not shown
    const chip: ToolItem = { kind: 'tool', id, name, input, status: 'running' };
    this.tools.set(id, chip);
    this.turn.items.push(chip);
  }

  private lane(id: string, agent: string | undefined, label: string | undefined): Lane {
    let lane = this.lanes.get(id);
    if (!lane) {
      lane = { id, agent: agent || 'agent', label: label || 'Working…', status: 'running', tools: 0, last: '' };
      this.lanes.set(id, lane);
      this.turn.lanes.push(lane);
    } else {
      if (agent && lane.agent === 'agent') lane.agent = agent;
      if (label && lane.label === 'Working…') lane.label = label;
    }
    return lane;
  }

  private laneByAgent(agentId: string): Lane | undefined {
    return this.turn.lanes.find(l => l.agentId === agentId);
  }

  private plan(name: string, input: Record<string, any>) {
    if (name === 'TodoWrite' && Array.isArray(input.todos)) {
      this.turn.plan = input.todos.map((t: any, i: number) => ({
        id: String(t.id ?? i + 1), label: String(t.content ?? t.activeForm ?? ''), status: todoStatus(t.status),
      }));
    } else if (name === 'TaskCreate' && (input.subject || input.description)) {
      const step: PlanStep = { id: '', label: String(input.subject ?? input.description), status: 'pending' };
      this.turn.plan.push(step);
      this.pendingTasks.push(step);
    } else if (name === 'TaskUpdate' && input.taskId != null) {
      const step = this.turn.plan.find(s => s.id === String(input.taskId))
        ?? this.turn.plan[Number(input.taskId) - 1];
      if (!step) return;
      if (input.status === 'deleted') this.turn.plan = this.turn.plan.filter(s => s !== step);
      else if (input.status) step.status = todoStatus(input.status);
      if (input.subject) step.label = String(input.subject);
    }
  }

  private bindTaskId(text: string) {
    const step = this.pendingTasks.shift();
    if (!step) return;
    const m = /#(\d+)/.exec(text);
    step.id = m ? m[1] : String(this.turn.plan.indexOf(step) + 1);
  }
}

function todoStatus(s: unknown): StepStatus {
  if (s === 'completed' || s === 'done') return 'done';
  if (s === 'in_progress' || s === 'running') return 'running';
  if (s === 'failed') return 'failed';
  return 'pending';
}

function resultText(content: unknown): string {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.map((c: any) => c?.text ?? '').join('');
  return '';
}

/** A short, human label for a tool call: "Reading wiki/accounts/x.md". */
export function describeTool(name: string, input: Record<string, any>, root?: string): string {
  const path = (p: unknown) => relPath(String(p ?? ''), root);
  switch (name) {
    case 'Read': return `Reading ${path(input.file_path)}`;
    case 'Write': return `Writing ${path(input.file_path)}`;
    case 'Edit': case 'MultiEdit': return `Editing ${path(input.file_path)}`;
    case 'NotebookEdit': return `Editing ${path(input.notebook_path)}`;
    case 'Grep': return `Searching for “${input.pattern ?? ''}”${input.path ? ` in ${path(input.path)}` : ''}`;
    case 'Glob': return `Finding ${input.pattern ?? 'files'}`;
    case 'Bash': {
      const cmd = String(input.command ?? '');
      const script = /(scripts\/[\w.-]+\.py)/.exec(cmd);
      if (script) return `Running ${script[1]}`;
      return input.description ? String(input.description) : `Running ${cmd.split('\n')[0].slice(0, 60)}`;
    }
    case 'WebSearch': return `Searching the web: ${input.query ?? ''}`;
    case 'WebFetch': {
      try { return `Fetching ${new URL(String(input.url)).hostname}`; } catch { return 'Fetching a page'; }
    }
    case 'Skill': return `Using skill ${input.skill ?? input.command ?? ''}`.trim();
    case 'ToolSearch': return 'Loading tools';
  }
  if (name.startsWith('mcp__')) {
    const parts = name.split('__');
    return `${parts[1]?.replace(/^claude_ai_/, '').replace(/_/g, ' ')} · ${parts.slice(2).join(' ').replace(/_/g, ' ')}`;
  }
  return name;
}

/** Strip the repo root (or any absolute prefix up to a known top folder) from a path. */
export function relPath(p: string, root?: string): string {
  if (root && p.startsWith(root)) return p.slice(root.length).replace(/^[/\\]+/, '');
  const m = /(?:^|[/\\])((?:wiki|raw|knowledge|log|reps|scripts|templates|docs|evals|runner|\.claude|\.agents)[/\\].*)$/.exec(p);
  return m ? m[1] : p;
}

/** Parse a JSONL buffer, skipping blank and non-JSON lines (e.g. CLI warnings). */
export function parseLines(text: string): StreamEvent[] {
  const out: StreamEvent[] = [];
  for (const line of text.split('\n')) {
    const t = line.trim();
    if (!t.startsWith('{')) continue;
    try { out.push(JSON.parse(t)); } catch { /* partial or foreign line */ }
  }
  return out;
}
