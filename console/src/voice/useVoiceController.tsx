// Voice in the console (spec §4–5, §15–18): one place that turns speech into prompts and answers into
// speech, so App.tsx only places the pieces.
// - Tap the orb: a LIVE conversation (spec §18). What you say goes straight to Sales Mama (no read-back,
//   unless an account name is unsure), and the answer is spoken as it streams, sentence by sentence.
// - Hold the orb (or ⌥Space): push-to-talk with the read-back chip.
// - Spoken commands navigate the console; a bare "send it" / "approve" is answered, never sent.
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { AccountInfo } from '../../server/repo';
import { findMentions, SURE, withMentions, type Mention } from '../../shared/mentions';
import { answerText, leadOf, speakable, spokenAnswer } from '../../shared/speakable';
import { describeTool, type ToolItem } from '../../shared/stream';
import {
  ackFor, APPROVAL_REPLY, isApproval, LIVE_BYE, LIVE_GREETING, LIVE_QUEUED, NAV_PHRASES, parseCommand, toolCommand, VOICE_HELP,
  type Route, type VoiceCommand, type VoiceMode,
} from '../../shared/voice';
import { calendarKey, clearFocus, closeTop, focusTurn, openCanvas, openSource, scrollChat } from './navigate';
import type { ChatTurn } from '../useBridge';
import type { FollowUp } from '../chat/Composer';
import { IconSliders, IconSpeaker, IconSpeakerOff } from '../app/Icons';
import { useVoice } from './useVoice';
import { Captions, Orb, ReadBack, type OrbState, type ReadBackState } from './VoiceUI';
import { VoiceSettingsPanel } from './VoiceSettings';

interface Deps {
  turns: ChatTurn[]; accounts: AccountInfo[]; canAsk: boolean; live: boolean; followUps: FollowUp[]; route: Route;
  ask: (t: string, voice?: boolean) => void; stop: () => void; go: (r: Route) => void; newChat: () => void; queue: (t: string) => void;
  edit: (t: string) => void; openRecent: () => boolean; openPalette: () => void; showHelp: () => void;
}

/** Live mode speaks a short summary only: about 5 to 10 seconds (spec §18). The rest stays on screen. */
const LIVE_MAX_WORDS = 25;

export function useVoiceController(d: Deps) {
  const dep = useRef(d);
  dep.current = d;
  const [readback, setReadback] = useState<(ReadBackState & { callId?: string }) | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [lastHeard, setLastHeard] = useState('');
  const pendingCall = useRef<string | null>(null);        // realtime: the next turn answers this tool call
  const callFor = useRef(new Map<string, string>());
  const seen = useRef(new Set<string>());
  const spoken = useRef(new Set<string>());
  const liveTurns = useRef(new Set<string>());
  const livePending = useRef<string | null>(null);      // spoken while a run is going: sent (as voice) when it ends
  const focus = useRef<number | null>(null);               // the answer in focus for voice navigation (null = latest)

  /** Read answer i aloud, with where it is ("Answer 2 of 5"). */
  const readTurn = (i: number, withPosition: boolean) => {
    const x = dep.current, t = x.turns[i];
    if (!t) return;
    const s = spokenAnswer(t.turn, t.error);
    const where = withPosition ? `Answer ${i + 1} of ${x.turns.length}. ` : '';
    voiceRef.current?.say(`${where}${s.text || 'This answer has no summary; the details are on screen.'}`, 'answer', `nav-${t.id}-${Date.now()}`, 'mama');
  };

  const runCommand = useCallback((c: VoiceCommand) => {
    const x = dep.current;
    const v = voiceRef.current;
    const say = (text: string) => v?.say(text, 'notice');
    const inChat = () => { if (x.route !== 'chat') x.go('chat'); };
    const current = () => (focus.current ?? x.turns.length - 1);
    switch (c.kind) {
      case 'stop': v?.stopSpeaking(); if (x.live) x.stop(); break;
      case 'new_chat': focus.current = null; x.newChat(); say(NAV_PHRASES.newChat); break;
      case 'repeat': v?.repeat(); break;
      case 'end_conversation': endLive(); break;
      case 'help': x.showHelp(); say(VOICE_HELP); break;
      case 'speak_answers': v?.setSpeakAnswers(c.on); if (c.on) say('Okay, I will read answers aloud.'); break;
      case 'go':
        // "Go to today" while on the calendar means the calendar's today.
        if (c.route === 'today' && x.route === 'calendar') { calendarKey('t'); say(NAV_PHRASES.calToday); break; }
        x.go(c.route);
        say(NAV_PHRASES[c.route]);
        break;
      case 'pick': {
        const f = c.index < 0 ? x.followUps[x.followUps.length - 1] : x.followUps[c.index];
        if (f) send(f.prompt); else say('There is no suggestion with that number.');
        break;
      }
      case 'answer': {
        if (!x.turns.length) { say('There are no answers in this chat yet.'); break; }
        inChat();
        const n = x.turns.length, at = current();
        const i = c.to === 'first' ? 0 : c.to === 'last' ? n - 1 : c.to === 'prev' ? at - 1 : at + 1;
        if (i < 0) { say('That is the first answer.'); break; }
        if (i >= n) { say('That is the latest answer.'); break; }
        focus.current = i === n - 1 ? null : i;
        requestAnimationFrame(() => focusTurn(i));
        readTurn(i, true);
        break;
      }
      case 'read': {
        if (!x.turns.length) { say('There is nothing to read yet.'); break; }
        readTurn(current(), false);
        break;
      }
      case 'scroll': inChat(); if (c.to === 'bottom') { focus.current = null; clearFocus(); } scrollChat(c.to); if (c.to === 'top' || c.to === 'bottom') say(NAV_PHRASES[c.to]); break;
      case 'source': {
        inChat();
        const name = openSource(current(), c.index);
        if (!name) say(`This answer has no source ${c.index + 1}.`);
        else if (c.index < 6) say(NAV_PHRASES[`source${c.index + 1}` as keyof typeof NAV_PHRASES]);
        break;
      }
      case 'canvas': inChat(); say(openCanvas(current()) ? NAV_PHRASES.canvas : 'There is no view to open in this answer.'); break;
      case 'close': setSettingsOpen(false); closeTop(); say(NAV_PHRASES.close); break;
      case 'recent': if (!x.openRecent()) say('There are no saved chats yet.'); else { focus.current = null; say(NAV_PHRASES.recent); } break;
      case 'search': x.openPalette(); say(NAV_PHRASES.search); break;
      case 'period':
        if (x.route !== 'calendar') x.go('calendar');
        requestAnimationFrame(() => calendarKey(c.to === 'next' ? 'ArrowRight' : c.to === 'prev' ? 'ArrowLeft' : 't'));
        say(c.to === 'next' ? NAV_PHRASES.next : c.to === 'prev' ? NAV_PHRASES.prev : NAV_PHRASES.calToday);
        break;
      case 'calview':
        if (x.route !== 'calendar') x.go('calendar');
        requestAnimationFrame(() => calendarKey(c.view === 'day' ? 'd' : c.view === 'week' ? 'w' : 'm'));
        say(NAV_PHRASES[c.view]);
        break;
    }
  }, []);

  /** Send now, or queue behind the running turn (Composer v2 behaviour). */
  const send = useCallback((prompt: string, callId?: string) => {
    const x = dep.current;
    if (callId) pendingCall.current = callId;
    if (x.canAsk) x.ask(prompt); else x.queue(prompt);
  }, []);

  const showReadback = useCallback((heard: string, mode: VoiceMode | 'tool', callId?: string) => {
    const mentions = findMentions(heard, dep.current.accounts);
    dep.current.go('chat');
    setReadback({ id: `rb-${Date.now().toString(36)}`, heard, prompt: withMentions(heard, mentions), unsure: mentions.filter(m => m.conf < SURE),
      delayMs: mode === 'push' || mode === 'tap' ? 1500 : 1000, callId });
  }, []);

  const voice = useVoice({
    onFinal: (text, mode) => {
      setLastHeard(text);
      const cmd = parseCommand(text);
      if (cmd) { runCommand(cmd); return; }
      if (isApproval(text)) { voiceRef.current?.say(APPROVAL_REPLY, 'notice'); return; }
      if (mode === 'conversation') {
        // Live: straight to Sales Mama. Only an unsure account name stops to ask.
        const mentions = findMentions(text, dep.current.accounts);
        const unsure = mentions.filter(m => m.conf < SURE);
        if (unsure.length) {
          const opts = [unsure[0], ...unsure[0].alternatives].map(c => ('name' in c ? c.name : '') || c.id).slice(0, 3);
          voiceRef.current?.say(`Which account did you mean: ${opts.join(', or ')}? Pick it on screen.`, 'notice');
          showReadback(text, mode);
          return;
        }
        const prompt = withMentions(text, mentions);
        dep.current.go('chat');                              // a spoken question brings the chat into view
        if (dep.current.canAsk) dep.current.ask(prompt, true);
        else { livePending.current = prompt; voiceRef.current?.say(LIVE_QUEUED, 'notice'); }
        return;
      }
      showReadback(text, mode);
    },
    onToolPrompt: (callId, prompt) => {
      if (isApproval(prompt)) { voiceRef.current?.toolResult(callId, APPROVAL_REPLY); return; }
      const cmd = parseCommand(prompt);
      if (cmd) { runCommand(cmd); voiceRef.current?.toolResult(callId, 'Done.'); return; }
      showReadback(prompt, 'tool', callId);
    },
    onCommand: command => { const c = toolCommand(command); if (c) runCommand(c); },
  });
  const voiceRef = useRef(voice);
  voiceRef.current = voice;

  /** Live conversation: on with a greeting, off with a goodbye. GPT live is the same gesture with the realtime engine. */
  const liveOn = voice.mode === 'conversation';
  const cascadeLive = liveOn && voice.settings.engine === 'cascade';
  const startLive = useCallback(async () => {
    const v = voiceRef.current;
    await v.listen('conversation');
    if (v.settings.engine === 'cascade') v.say(LIVE_GREETING, 'notice');
  }, []);
  function endLive() {
    const v = voiceRef.current;
    if (v.mode !== 'conversation') return;
    v.cancelListen();
    v.say(LIVE_BYE, 'notice');
  }
  const toggleLive = useCallback(() => { if (voiceRef.current.mode === 'conversation') endLive(); else void startLive(); }, [startLive]);

  // Turns: an acknowledgement when one starts; in live mode the answer is spoken while it streams;
  // otherwise (speaker on) its lead line is spoken when it ends; in GPT live it goes back to GPT.
  useEffect(() => {
    for (const t of d.turns) {
      if (t.running && !seen.current.has(t.id)) {
        seen.current.add(t.id);
        focus.current = null;
        clearFocus();
        if (pendingCall.current) { callFor.current.set(t.id, pendingCall.current); pendingCall.current = null; }
        else if (cascadeLive) { liveTurns.current.add(t.id); voice.say(ackFor(t.prompt), 'ack'); }
        else if (voice.speakAnswers && !voice.live) voice.say(ackFor(t.prompt), 'ack');
      }
      if (liveTurns.current.has(t.id) && !t.running && !spoken.current.has(t.id)) {
        // Live: one short summary when the answer is ready.
        spoken.current.add(t.id);
        const short = t.error ? speakable(t.error.message, LIVE_MAX_WORDS).text : speakable(leadOf(answerText(t.turn.items)), LIVE_MAX_WORDS).text;
        const note = !t.error && t.turn.denied.length ? ' Some steps need your approval in Claude Code.' : '';
        voice.say(`${short || 'Done. It is on screen.'}${note}`, 'answer', t.id, 'mama');
        continue;
      }
      if (!t.running && seen.current.has(t.id) && !spoken.current.has(t.id)) {
        spoken.current.add(t.id);
        const s = spokenAnswer(t.turn, t.error);
        const call = callFor.current.get(t.id);
        if (call) voice.toolResult(call, s.text || 'Done. The details are on screen.');
        else if (voice.speakAnswers && s.text) voice.say(s.text, 'answer', t.id, 'mama');
      }
    }
  }, [d.turns, voice, cascadeLive]);

  // A request spoken during a run goes out (still as voice) as soon as the run ends.
  useEffect(() => {
    if (d.canAsk && livePending.current) { const p = livePending.current; livePending.current = null; d.ask(p, true); }
  }, [d.canAsk, d]);

  // Keys: hold ⌥Space to talk, ⌥⇧Space for live mode, ⌘. to repeat, Esc stops the voice first.
  useEffect(() => {
    let holding = false;
    const down = (e: KeyboardEvent) => {
      const v = voiceRef.current;
      if (e.code === 'Space' && e.altKey) {
        e.preventDefault();
        if (e.repeat) return;
        if (e.shiftKey) { toggleLive(); return; }
        holding = true;
        void v.listen('push');
        return;
      }
      if (e.key === '.' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); v.repeat(); return; }
      if (e.key === 'Escape' && v.speaking) { v.stopSpeaking(); e.stopPropagation(); }
    };
    const up = (e: KeyboardEvent) => {
      if (holding && (e.code === 'Space' || e.key === 'Alt')) { holding = false; void voiceRef.current.release(); }
    };
    window.addEventListener('keydown', down, true);
    window.addEventListener('keyup', up, true);
    return () => { window.removeEventListener('keydown', down, true); window.removeEventListener('keyup', up, true); };
  }, [toggleLive]);

  const onSendRb = useCallback((prompt: string) => {
    setReadback(rb => { if (rb) { dep.current.go('chat'); send(prompt, rb.callId); } return null; });
  }, [send]);
  const onEditRb = useCallback((prompt: string) => {
    setReadback(rb => { if (rb?.callId) voiceRef.current.toolResult(rb.callId, 'Okay, edit it on screen.'); return null; });
    dep.current.edit(prompt);
  }, []);
  const onCancelRb = useCallback(() => {
    setReadback(rb => { if (rb?.callId) voiceRef.current.toolResult(rb.callId, 'Okay, cancelled.'); return null; });
  }, []);
  const onPick = useCallback((m: Mention, id: string | null) => {
    setReadback(rb => {
      if (!rb) return rb;
      const unsure = rb.unsure.filter(u => u.start !== m.start);
      const prompt = id ? rb.prompt.replace(m.said, `@${id}`) : rb.prompt;
      return { ...rb, unsure, prompt };
    });
  }, []);

  const orbState: OrbState = voice.error ? 'error' : readback ? 'confirming' : voice.speaking ? 'speaking'
    : d.live ? 'thinking' : voice.mic !== 'idle' ? voice.mic : voice.available === false ? 'error' : 'idle';

  const orbEl = (
    <Orb state={orbState} level={voice.level} conversation={liveOn}
      onHold={() => { if (!liveOn) void voice.listen('push'); }} onRelease={() => void voice.release()}
      onTap={toggleLive} onStop={voice.stopSpeaking} />
  );
  const orb: ReactNode = (
    <>
      {orbEl}
      <button type="button" className="convo-btn" aria-pressed={liveOn} onClick={toggleLive}
        title={liveOn ? 'End the live conversation (⌥⇧Space)' : 'Start a live conversation (⌥⇧Space). Hold the mic to say one thing.'}>
        {liveOn ? 'END LIVE' : voice.settings.engine === 'realtime' ? 'GPT LIVE' : 'GO LIVE'}
      </button>
    </>
  );

  const above: ReactNode = (
    <>
      {voice.error && <div className="voice-toast" role="alert">{voice.error}</div>}
      {readback && <ReadBack rb={readback} onSend={onSendRb} onEdit={onEditRb} onCancel={onCancelRb} onPick={onPick} />}
      {!liveOn && !readback && voice.mic !== 'idle' && (voice.partial || voice.heard
        ? <Captions text={voice.partial || voice.heard} words={[]} clock={voice.clock} listening />
        : <Captions text="Listening… try “brief me on an account”, “previous answer” or “what can I say?”" words={[]} clock={voice.clock} listening />)}
      {!liveOn && !readback && voice.caption && voice.caption.text && <Captions text={voice.caption.text} words={voice.caption.words} clock={voice.clock} agent={voice.caption.agent} />}
    </>
  );

  // The live panel (every page): what you said, what Mama is saying, what she is doing.
  const running = d.turns.find(t => t.running);
  const tool = running ? [...running.turn.items].reverse().find((i): i is ToolItem => i.kind === 'tool' && i.status === 'running') : undefined;
  const doing = running ? (tool ? describeTool(tool.name, tool.input) : running.turn.lanes.some(l => l.status === 'running') ? 'Agents working…' : 'Thinking…') : '';
  const status = voice.speaking ? 'Mama is speaking. Talk to interrupt.' : running ? `Working: ${doing}` : voice.mic === 'hearing' ? 'Hearing you…' : 'Listening. Just talk.';
  const livePanel: ReactNode = liveOn ? (
    <section className="live-panel" aria-label="Live conversation with Sales Mama">
      <div className="lp-head">
        {orbEl}
        <div className="lp-status"><b>{voice.live ? 'GPT LIVE' : 'LIVE'}</b><span className={running && !voice.speaking ? 'shimmer' : undefined}>{status}</span></div>
        <button type="button" className="rb-btn" onClick={endLive}>End</button>
      </div>
      {(voice.partial || lastHeard || voice.heard) && <p className="lp-you"><span>You</span>{voice.partial || voice.heard || lastHeard}</p>}
      {voice.caption?.text && <Captions text={voice.caption.text} words={voice.caption.words} clock={voice.clock} agent="mama" />}
      {voice.error && <p className="lp-err">{voice.error}</p>}
      {readback && d.route !== 'chat' && <p className="lp-err">Pick the account in the chat.</p>}
    </section>
  ) : null;

  const headerExtra: ReactNode = (
    <>
      {d.route !== 'chat' && !liveOn && <span className="hdr-orb">{orbEl}</span>}
      {liveOn && (
        <button type="button" className="mic-on" onClick={endLive} title="End the live conversation">
          <i aria-hidden="true" />{voice.live ? 'GPT LIVE' : 'LIVE'}
        </button>
      )}
      <button type="button" className={`icon-btn${voice.speakAnswers ? ' speak-on' : ''}`} onClick={() => voice.setSpeakAnswers(!voice.speakAnswers)}
        aria-pressed={voice.speakAnswers} aria-label={voice.speakAnswers ? 'Answers are spoken. Turn off' : 'Speak answers aloud'} title={voice.speakAnswers ? 'Speaking answers' : 'Speak answers'}>
        {voice.speakAnswers ? <IconSpeaker size={18} /> : <IconSpeakerOff size={18} />}
      </button>
      <button type="button" className="icon-btn voice-gear" onClick={() => setSettingsOpen(o => !o)} aria-expanded={settingsOpen} aria-label="Voice settings" title="Voice settings">
        <IconSliders size={18} />
      </button>
    </>
  );

  const settings = useMemo(() => (settingsOpen ? <VoiceSettingsPanel voice={voice} onClose={() => setSettingsOpen(false)} /> : null), [settingsOpen, voice]);
  const panel: ReactNode = <>{settings}{livePanel}</>;

  return { voice, orb, above, headerExtra, panel };
}
