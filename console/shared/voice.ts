// Voice protocol and pure helpers (voice spec §4.2–4.3, §5, §15). Providers are configurable:
// - cascade (default): STT from Inworld, OpenAI or ElevenLabs, then the console engine (Claude Code
//   or Codex) answers, then TTS from Inworld, OpenAI or ElevenLabs. Speech is ears and mouth only.
// - realtime ("GPT live", OpenAI Realtime): GPT handles the conversation, but every work question goes
//   to Sales Mama through one tool, and GPT speaks only what Sales Mama answered (strict by default).
// Audio travels as binary WebSocket frames on /mama/voice: mic → server PCM16 16 kHz mono,
// server → browser PCM16 24 kHz mono. Everything else is JSON.

export type VoiceMode = 'push' | 'tap' | 'conversation';
export type VoiceState = 'off' | 'idle' | 'listening' | 'hearing' | 'confirming' | 'thinking' | 'speaking' | 'error';
export type Provider = 'inworld' | 'openai' | 'elevenlabs';
export type Engine = 'cascade' | 'realtime';

export const PROVIDERS: Provider[] = ['inworld', 'openai', 'elevenlabs'];
export const PROVIDER_NAME: Record<Provider, string> = { inworld: 'Inworld', openai: 'OpenAI', elevenlabs: 'ElevenLabs' };

export const MIC_RATE = 16_000;
export const SPEAKER_RATE = 24_000;

export interface VoiceSettings {
  engine: Engine;
  stt: Provider;
  tts: Provider;
  /** Voice per TTS provider, plus the OpenAI Realtime voice. */
  voices: Record<Provider | 'realtime', string>;
  rate: number;
  lang: string;
  /** Realtime only: GPT may only relay Sales Mama's answers (no free talk). */
  strict: boolean;
}

/** Male voices by default (2026-11-28). Inworld voices were checked by pitch (median F0 < 160 Hz). */
export const DEFAULT_SETTINGS: VoiceSettings = {
  engine: 'cascade', stt: 'inworld', tts: 'inworld',
  voices: { inworld: 'Junhao', openai: 'onyx', elevenlabs: 'JBFqnCBsd6RMkjVDRZzb', realtime: 'cedar' },
  rate: 1, lang: 'en', strict: true,
};

export interface VoiceOption { id: string; name: string; langs?: string[]; gender?: 'male' | 'female' | ''; note?: string }

/** Curated male voices shown first in the picker. */
export const MALE_VOICES: Record<Provider | 'realtime', VoiceOption[]> = {
  inworld: [
    { id: 'Junhao', name: 'Junhao', gender: 'male', note: 'Singaporean English, 109 Hz' },
    { id: 'Zherong', name: 'Zherong', gender: 'male', note: 'Singaporean English, 120 Hz' },
    { id: 'Boonleng', name: 'Boonleng', gender: 'male', note: 'Singaporean English, 137 Hz' },
    { id: 'Nikhil', name: 'Nikhil', gender: 'male', note: 'Indian English, 131 Hz' },
    { id: 'Vikram', name: 'Vikram', gender: 'male', note: 'Indian English, 141 Hz' },
    { id: 'Aditya', name: 'Aditya', gender: 'male', note: 'Indian English, 150 Hz' },
    { id: 'Dennis', name: 'Dennis', gender: 'male', note: 'American English, 131 Hz' },
  ],
  openai: [
    { id: 'onyx', name: 'Onyx', gender: 'male', note: 'deep' },
    { id: 'ash', name: 'Ash', gender: 'male' },
    { id: 'echo', name: 'Echo', gender: 'male' },
    { id: 'verse', name: 'Verse', gender: 'male' },
    { id: 'ballad', name: 'Ballad', gender: 'male' },
    { id: 'fable', name: 'Fable', gender: 'male', note: 'British' },
  ],
  elevenlabs: [
    { id: 'JBFqnCBsd6RMkjVDRZzb', name: 'George', gender: 'male', note: 'warm, British' },
    { id: 'nPczCjzI2devNBz1zQrb', name: 'Brian', gender: 'male', note: 'deep, American' },
    { id: 'pNInz6obpgDQGcFmaJgB', name: 'Adam', gender: 'male', note: 'American' },
    { id: 'onwK4e9ZLuTAKqWW03F9', name: 'Daniel', gender: 'male', note: 'British, news' },
  ],
  realtime: [
    { id: 'cedar', name: 'Cedar', gender: 'male', note: 'recommended for gpt-realtime' },
    { id: 'ash', name: 'Ash', gender: 'male' },
    { id: 'echo', name: 'Echo', gender: 'male' },
    { id: 'verse', name: 'Verse', gender: 'male' },
    { id: 'ballad', name: 'Ballad', gender: 'male' },
  ],
};

export function mergeSettings(base: VoiceSettings, s: Partial<VoiceSettings> | undefined): VoiceSettings {
  return { ...base, ...(s ?? {}), voices: { ...base.voices, ...(s?.voices ?? {}) } };
}

export type VoiceClientMsg =
  | { type: 'listen'; mode: VoiceMode }                        // open a mic turn; binary frames follow
  | { type: 'listen_end' }                                     // push-to-talk released: finish the turn
  | { type: 'listen_cancel' }                                  // discard what was heard / end a live session
  | { type: 'speak'; id: string; text: string; agent?: string; kind?: 'answer' | 'ack' | 'notice' }
  | { type: 'speak_stop' }                                     // barge-in or Esc
  | { type: 'settings'; settings: Partial<VoiceSettings> }
  | { type: 'tool_result'; callId: string; text: string }     // realtime: Sales Mama's spoken answer for GPT to say
  | { type: 'say_stream'; id: string; text: string; final?: boolean; agent?: string };  // live mode: speak as the answer streams

export interface Word { w: string; start: number; end: number }

export interface ProviderStatus { available: boolean; stt: boolean; tts: boolean; realtime: boolean; keyFile: string; voices: VoiceOption[] }

export type VoiceServerMsg =
  | { type: 'ready'; available: boolean; providers: Record<Provider, ProviderStatus>; defaults: VoiceSettings; problem?: { message: string; fix?: string } }
  | { type: 'speech_started' }                                 // the user started talking (barge-in signal)
  | { type: 'partial'; text: string }
  | { type: 'final'; text: string }                            // cascade: the transcript, for the read-back
  | { type: 'heard'; text: string }                            // realtime: what GPT heard (display only, never sent as a prompt)
  | { type: 'heard_nothing' }
  | { type: 'speech_begin'; id: string; text: string; agent?: string }
  | { type: 'speech_text'; id: string; text: string }          // realtime: the caption grows as GPT speaks
  | { type: 'words'; id: string; words: Word[] }               // seconds from the start of this speech
  | { type: 'speech_end'; id: string; interrupted: boolean }
  | { type: 'tool_prompt'; callId: string; prompt: string }    // realtime: GPT asks Sales Mama (goes through the read-back)
  | { type: 'tool_command'; callId: string; command: string }  // realtime: stop, new chat, open calendar…
  | { type: 'mismatch'; spoken: string; source: string }       // realtime: GPT said a number Sales Mama did not
  | { type: 'live'; on: boolean }                              // realtime session opened or closed
  | { type: 'voice_error'; message: string; fix?: string };

// ---------------------------------------------------------------------------------------------
// Acknowledgements (spec §5.3): short, fixed, pre-synthesised once and cached, so they cost
// nothing per use and play at once. Chosen by the skill in the prompt.
// ---------------------------------------------------------------------------------------------
export const ACKS: Record<string, string> = {
  'mama-day': 'Getting your day ready.',
  'mama-book': 'Checking your book.',
  'mama-brief': 'Pulling the brief.',
  'mama-research': 'Researching that now.',
  'mama-draft': 'Drafting that for you.',
  'mama-send': 'Preparing the preview.',
  'mama-replies': 'Going through your replies.',
  'mama-schedule': 'Checking the calendar.',
  'mama-manager': 'Opening the cockpit.',
  'mama-allocate': 'Working out the allocation.',
  'mama-weekly': 'Running the weekly review.',
  'company-check': 'Checking that company.',
  'company-insights': 'Looking at the market.',
  default: 'On it.',
};

export function ackFor(prompt: string): string {
  const m = /^\/([\w-]+)/.exec(prompt.trim());
  if (m && ACKS[m[1]]) return ACKS[m[1]];
  const p = prompt.toLowerCase();
  if (/\bbrief\b/.test(p)) return ACKS['mama-brief'];
  if (/\b(draft|follow-?up|write)\b/.test(p)) return ACKS['mama-draft'];
  if (/\b(calendar|meeting|schedule|appointment)s?\b/.test(p)) return ACKS['mama-schedule'];
  if (/\b(my day|today)\b/.test(p)) return ACKS['mama-day'];
  return ACKS.default;
}

/** Live conversation (tap the orb): fixed lines, cached like acknowledgements. */
export const LIVE_GREETING = 'Sales Mama here. I am listening.';
export const LIVE_BYE = 'Okay. Talk soon.';
export const LIVE_MORE = 'The rest is on screen.';

/** Principle 12: the voice never holds the pen. A bare spoken approval is answered, not sent. */
export const APPROVAL_REPLY = 'Sending needs your click in Claude Code. I can prepare the preview.';
export function isApproval(text: string): boolean {
  const t = text.toLowerCase().replace(/[^\w\s']/g, ' ').replace(/\s+/g, ' ').trim();
  return /^(?:(?:yes|yeah|yep|ok|okay|sure|please|go ahead|do it)\s*)*(?:and\s+)?(?:send|approve|confirm|ship|submit|assign)(?:\s+(?:it|them|this|that|all|everything|the (?:drafts?|emails?|messages?|batch|allocation|leads)))*(?:\s+(?:now|please|out))*$/.test(t)
    || /^(?:yes|yeah|ok|okay)\s+(?:send|approve)\b/.test(t);
}

// ---------------------------------------------------------------------------------------------
// Spoken commands (spec §5.2): the same verbs as the keyboard map, nothing new.
// ---------------------------------------------------------------------------------------------
export type Route = 'today' | 'chat' | 'calendar' | 'book' | 'reports';
/** Voice navigation (spec §5.2, §16): every verb maps to something the keyboard or a click already does. */
export type VoiceCommand =
  | { kind: 'stop' } | { kind: 'new_chat' } | { kind: 'repeat' } | { kind: 'end_conversation' }
  | { kind: 'go'; route: Route }
  | { kind: 'pick'; index: number }                                  // a follow-up chip
  | { kind: 'answer'; to: 'prev' | 'next' | 'first' | 'last' }       // move through the chat and read it
  | { kind: 'read' }                                                 // read the answer in focus
  | { kind: 'scroll'; to: 'up' | 'down' | 'top' | 'bottom' }
  | { kind: 'source'; index: number }                                // open numbered source n of the answer in focus
  | { kind: 'canvas' } | { kind: 'close' } | { kind: 'recent' } | { kind: 'search' } | { kind: 'help' }
  | { kind: 'period'; to: 'prev' | 'next' | 'today' }               // calendar ← → t
  | { kind: 'calview'; view: 'day' | 'week' | 'month' }              // calendar d w m
  | { kind: 'speak_answers'; on: boolean };

const ORDINALS: Record<string, number> = { first: 0, one: 0, '1st': 0, '1': 0, second: 1, two: 1, '2nd': 1, '2': 1, third: 2, three: 2, '3rd': 2, '3': 2,
  fourth: 3, four: 3, '4th': 3, '4': 3, fifth: 4, five: 4, '5': 4, sixth: 5, six: 5, '6': 5, last: -1,
  // STT homophones for spoken numbers ("open source too").
  too: 1, to: 1, for: 3, fore: 3, won: 0 };

export function parseCommand(text: string): VoiceCommand | null {
  const t = text.toLowerCase().replace(/[^\w\s']/g, ' ').replace(/\s+/g, ' ').trim()
    .replace(/^(?:hey |ok |okay )?(?:mama|sales mama)\s*/, '').replace(/^(?:please |can you |could you )/, '').replace(/\s*please$/, '');
  if (/^(?:stop|cancel|shush|stop talking|never mind|nevermind)$/.test(t)) return { kind: 'stop' };
  if (/^(?:new chat|start (?:a )?new chat|start over|clear (?:the )?chat)$/.test(t)) return { kind: 'new_chat' };
  if (/^(?:read (?:that|it) again|say (?:that|it) again|repeat(?: that)?|again|what did you say)$/.test(t)) return { kind: 'repeat' };
  if (/^(?:that's all|thats all|goodbye|bye|end (?:the )?conversation|stop listening|thank you that's all)$/.test(t)) return { kind: 'end_conversation' };
  if (/^(?:what can i say|help|voice help|voice commands|what can you do)$/.test(t)) return { kind: 'help' };
  if (/^(?:mute|be quiet|quiet|stop speaking(?: answers)?|don't read answers|silent mode)$/.test(t)) return { kind: 'speak_answers', on: false };
  if (/^(?:unmute|speak answers|read answers(?: aloud)?|talk to me|speak up)$/.test(t)) return { kind: 'speak_answers', on: true };

  // Moving through the chat.
  if (/^(?:previous|prev|go back|back|earlier|the one before|before that)(?: answer| one| message| reply)?$/.test(t)) return { kind: 'answer', to: 'prev' };
  if (/^(?:next|forward|the one after|after that)(?: answer| one| message| reply)$|^(?:go forward|forward)$/.test(t)) return { kind: 'answer', to: 'next' };
  if (/^(?:(?:go to |read )?the )?(?:first|oldest|top) (?:answer|message|reply)$/.test(t)) return { kind: 'answer', to: 'first' };
  if (/^(?:(?:go to |read )?the )?(?:last|latest|newest|most recent) (?:answer|message|reply)$/.test(t)) return { kind: 'answer', to: 'last' };
  if (/^(?:read (?:it|that|this|the answer|this answer|that answer|it out|it aloud|it to me)|read)$/.test(t)) return { kind: 'read' };
  if (/^(?:scroll|page|go) up$/.test(t)) return { kind: 'scroll', to: 'up' };
  if (/^(?:scroll|page|go) down$/.test(t)) return { kind: 'scroll', to: 'down' };
  if (/^(?:go to |scroll to )?(?:the )?top$/.test(t)) return { kind: 'scroll', to: 'top' };
  if (/^(?:go to |scroll to |jump to )?(?:the )?(?:bottom|latest|end)$/.test(t)) return { kind: 'scroll', to: 'bottom' };
  const src = /^(?:open |show |show me )?(?:the )?source(?: number)? (\w+)$|^(?:open |show )(?:the )?(\w+) source$/.exec(t);
  if (src) { const k = src[1] ?? src[2]; if (k in ORDINALS && ORDINALS[k] >= 0) return { kind: 'source', index: ORDINALS[k] }; }
  if (/^(?:open (?:it |that |this )?in (?:the )?canvas|open (?:the )?canvas|expand(?: it| that)?|make it bigger|full screen)$/.test(t)) return { kind: 'canvas' };
  if (/^(?:close(?: it| that| this| the (?:drawer|canvas|panel|source|settings|palette|window|sheet))?|dismiss|hide(?: it| that)?)$/.test(t)) return { kind: 'close' };
  if (/^(?:open|resume|continue|go back to)(?: my)? (?:last|previous|recent) (?:chat|conversation)$/.test(t)) return { kind: 'recent' };
  if (/^(?:search|open search|find|command palette|open (?:the )?command palette)$/.test(t)) return { kind: 'search' };

  // Calendar.
  if (/^(?:next|following) (?:week|month|day)$|^(?:go )?forward(?: a| one)? (?:week|month|day)$/.test(t)) return { kind: 'period', to: 'next' };
  if (/^(?:previous|last) (?:week|month|day)$|^(?:go )?back(?: a| one)? (?:week|month|day)$/.test(t)) return { kind: 'period', to: 'prev' };
  if (/^(?:this week|this month|go to today|back to today|jump to today)$/.test(t)) return { kind: 'period', to: 'today' };
  const cv = /^(?:show |switch to |open )?(?:the |a )?(day|week|month) view$|^(?:show )?(?:the )?(day|week|month)$/.exec(t);
  if (cv) return { kind: 'calview', view: (cv[1] ?? cv[2]) as 'day' | 'week' | 'month' };

  const go = /^(?:open|show|go to|show me|take me to)(?: me)?(?: the| my)? (today|chat|calendar|book|reports?|schedule|agenda|accounts)(?: view| page)?$/.exec(t);
  if (go) {
    const r = go[1];
    return { kind: 'go', route: (r.startsWith('report') ? 'reports' : r === 'schedule' || r === 'agenda' ? 'calendar' : r === 'accounts' ? 'book' : r) as Route };
  }
  const pick = /^(?:(?:do |run |pick |choose |take )?the )?(first|second|third|fourth|last|one|two|three|four|1st|2nd|3rd)(?: one| option| suggestion)?$/.exec(t)
    ?? /^(?:option|number|suggestion) (one|two|three|four|too|to|for|1|2|3|4)$/.exec(t);
  if (pick) return { kind: 'pick', index: ORDINALS[pick[1]] };
  return null;
}

/** The realtime voice_command tool's argument → a command (same vocabulary as parseCommand). */
export const TOOL_COMMANDS = [
  'stop', 'new_chat', 'repeat', 'end_conversation', 'help', 'mute', 'unmute',
  'open_today', 'open_chat', 'open_calendar', 'open_book', 'open_reports',
  'previous_answer', 'next_answer', 'first_answer', 'last_answer', 'read_answer',
  'scroll_up', 'scroll_down', 'scroll_top', 'scroll_bottom',
  'open_source_1', 'open_source_2', 'open_source_3', 'open_source_4', 'open_source_5', 'open_source_6',
  'open_canvas', 'close', 'recent_chat', 'search',
  'next_period', 'previous_period', 'today_period', 'day_view', 'week_view', 'month_view',
  'pick_1', 'pick_2', 'pick_3', 'pick_4',
];
export function toolCommand(command: string): VoiceCommand | null {
  const c = command.trim().toLowerCase();
  if (!TOOL_COMMANDS.includes(c)) return null;
  const simple: Record<string, VoiceCommand> = {
    stop: { kind: 'stop' }, new_chat: { kind: 'new_chat' }, repeat: { kind: 'repeat' }, end_conversation: { kind: 'end_conversation' }, help: { kind: 'help' },
    mute: { kind: 'speak_answers', on: false }, unmute: { kind: 'speak_answers', on: true },
    previous_answer: { kind: 'answer', to: 'prev' }, next_answer: { kind: 'answer', to: 'next' }, first_answer: { kind: 'answer', to: 'first' }, last_answer: { kind: 'answer', to: 'last' },
    read_answer: { kind: 'read' }, scroll_up: { kind: 'scroll', to: 'up' }, scroll_down: { kind: 'scroll', to: 'down' }, scroll_top: { kind: 'scroll', to: 'top' }, scroll_bottom: { kind: 'scroll', to: 'bottom' },
    open_canvas: { kind: 'canvas' }, close: { kind: 'close' }, recent_chat: { kind: 'recent' }, search: { kind: 'search' },
    next_period: { kind: 'period', to: 'next' }, previous_period: { kind: 'period', to: 'prev' }, today_period: { kind: 'period', to: 'today' },
    day_view: { kind: 'calview', view: 'day' }, week_view: { kind: 'calview', view: 'week' }, month_view: { kind: 'calview', view: 'month' },
  };
  if (simple[c]) return simple[c];
  const go = /^open_(today|chat|calendar|book|reports)$/.exec(c);
  if (go) return { kind: 'go', route: go[1] as Route };
  const s = /^open_source_([1-6])$/.exec(c);
  if (s) return { kind: 'source', index: Number(s[1]) - 1 };
  const pick = /^pick_([1-4])$/.exec(c);
  if (pick) return { kind: 'pick', index: Number(pick[1]) - 1 };
  return null;
}

/** Spoken help: short enough to hear, and the full list is on screen. */
export const VOICE_HELP = 'You can ask me anything about your work. To move around, say: previous answer, next answer, read it, open source two, open in canvas, scroll up, open the calendar, next week, open my last chat, new chat, or stop.';

/** A word-timed caption: the index of the word being spoken at time t (seconds), or -1. */
export function wordAt(words: Word[], t: number): number {
  let idx = -1;
  for (let i = 0; i < words.length; i++) { if (words[i].start <= t) idx = i; else break; }
  return idx;
}

// ---------------------------------------------------------------------------------------------
// Grounding guard for realtime (spec §15.3): every number GPT says must appear in what Sales Mama
// answered. Spelled-out numbers are normalised ("three" = 3). Times, money and percentages count.
// ---------------------------------------------------------------------------------------------
const NUMWORDS: Record<string, number> = { zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
  eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19, twenty: 20,
  thirty: 30, forty: 40, fifty: 50, sixty: 60, seventy: 70, eighty: 80, ninety: 90, hundred: 100 };

export function numbersIn(text: string): number[] {
  const out: number[] = [];
  const t = text.toLowerCase().replace(/(\d),(\d{3})/g, '$1$2');
  for (const m of t.matchAll(/\d+(?:\.\d+)?/g)) out.push(Number(m[0]));
  const words = t.replace(/-/g, ' ').split(/[^a-z]+/);
  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    if (!(w in NUMWORDS)) continue;
    if (w === 'one' && /^(?:no|any|every|some|this|that|which|the)$/.test(words[i - 1] ?? '')) continue; // "the one", "no one"
    let n = NUMWORDS[w];
    if (n >= 20 && n % 10 === 0 && words[i + 1] in NUMWORDS && NUMWORDS[words[i + 1]] < 10) { n += NUMWORDS[words[i + 1]]; i++; }
    out.push(n);
  }
  return out;
}

/** Numbers GPT said that Sales Mama's answer does not contain (empty = grounded). */
export function ungroundedNumbers(spoken: string, source: string): number[] {
  const have = new Set(numbersIn(source));
  // A clock time "2 pm" may be said as "two" or "fourteen hundred"; accept 12-hour equivalents.
  for (const n of [...have]) if (n > 12 && n < 24) have.add(n - 12);
  return [...new Set(numbersIn(spoken))].filter(n => !have.has(n));
}
