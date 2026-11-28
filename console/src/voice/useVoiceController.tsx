// Voice in the console (spec §4–5, §15): one place that turns speech into prompts and answers into
// speech, so App.tsx only places the pieces.
// - A spoken request goes through the read-back, then `ask` (the same path as typed text).
// - Spoken commands use the keyboard map's verbs; a bare "send it" / "approve" is answered, never sent.
// - When a turn ends, its lead line is spoken (or, in GPT live, handed back to GPT to say).
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { AccountInfo } from '../../server/repo';
import { findMentions, SURE, withMentions, type Mention } from '../../shared/mentions';
import { spokenAnswer } from '../../shared/speakable';
import { ackFor, APPROVAL_REPLY, isApproval, parseCommand, toolCommand, VOICE_HELP, type Route, type VoiceCommand, type VoiceMode } from '../../shared/voice';
import { calendarKey, clearFocus, closeTop, focusTurn, openCanvas, openSource, scrollChat } from './navigate';
import type { ChatTurn } from '../useBridge';
import type { FollowUp } from '../chat/Composer';
import { IconSliders, IconSpeaker, IconSpeakerOff } from '../app/Icons';
import { useVoice } from './useVoice';
import { Captions, Orb, ReadBack, type OrbState, type ReadBackState } from './VoiceUI';
import { VoiceSettingsPanel } from './VoiceSettings';

interface Deps {
  turns: ChatTurn[]; accounts: AccountInfo[]; canAsk: boolean; live: boolean; followUps: FollowUp[]; route: Route;
  ask: (t: string) => void; stop: () => void; go: (r: Route) => void; newChat: () => void; queue: (t: string) => void;
  edit: (t: string) => void; openRecent: () => boolean; openPalette: () => void; showHelp: () => void;
}

export function useVoiceController(d: Deps) {
  const dep = useRef(d);
  dep.current = d;
  const [readback, setReadback] = useState<(ReadBackState & { callId?: string }) | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const pendingCall = useRef<string | null>(null);        // realtime: the next turn answers this tool call
  const callFor = useRef(new Map<string, string>());
  const seen = useRef(new Set<string>());
  const spoken = useRef(new Set<string>());
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
      case 'new_chat': focus.current = null; x.newChat(); break;
      case 'repeat': v?.repeat(); break;
      case 'end_conversation': v?.cancelListen(); break;
      case 'help': x.showHelp(); say(VOICE_HELP); break;
      case 'speak_answers': v?.setSpeakAnswers(c.on); if (c.on) say('Okay, I will read answers aloud.'); break;
      case 'go':
        // "Go to today" while on the calendar means the calendar's today.
        if (c.route === 'today' && x.route === 'calendar') { calendarKey('t'); break; }
        x.go(c.route);
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
      case 'scroll': inChat(); if (c.to === 'bottom') { focus.current = null; clearFocus(); } scrollChat(c.to); break;
      case 'source': {
        inChat();
        const name = openSource(current(), c.index);
        if (!name) say(`This answer has no source ${c.index + 1}.`);
        break;
      }
      case 'canvas': inChat(); if (!openCanvas(current())) say('There is no view to open in this answer.'); break;
      case 'close': setSettingsOpen(false); closeTop(); break;
      case 'recent': if (!x.openRecent()) say('There are no saved chats yet.'); else focus.current = null; break;
      case 'search': x.openPalette(); break;
      case 'period':
        if (x.route !== 'calendar') x.go('calendar');
        requestAnimationFrame(() => calendarKey(c.to === 'next' ? 'ArrowRight' : c.to === 'prev' ? 'ArrowLeft' : 't'));
        break;
      case 'calview':
        if (x.route !== 'calendar') x.go('calendar');
        requestAnimationFrame(() => calendarKey(c.view === 'day' ? 'd' : c.view === 'week' ? 'w' : 'm'));
        break;
    }
  }, []);

  /** Send now, or queue behind the running turn (Composer v2 behaviour). */
  const send = useCallback((prompt: string, callId?: string) => {
    const x = dep.current;
    x.go('chat');
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
      const cmd = parseCommand(text);
      if (cmd) { runCommand(cmd); return; }
      if (isApproval(text)) { voiceRef.current?.say(APPROVAL_REPLY, 'notice'); return; }
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

  // Speak when a turn starts (a cached acknowledgement) and when it ends (the lead line).
  useEffect(() => {
    for (const t of d.turns) {
      if (t.running && !seen.current.has(t.id)) {
        seen.current.add(t.id);
        focus.current = null;
        clearFocus();
        if (pendingCall.current) { callFor.current.set(t.id, pendingCall.current); pendingCall.current = null; }
        else if (voice.speakAnswers && !voice.live) voice.say(ackFor(t.prompt), 'ack');
      }
      if (!t.running && seen.current.has(t.id) && !spoken.current.has(t.id)) {
        spoken.current.add(t.id);
        const s = spokenAnswer(t.turn, t.error);
        const call = callFor.current.get(t.id);
        if (call) voice.toolResult(call, s.text || 'Done. The details are on screen.');
        else if (voice.speakAnswers && s.text) voice.say(s.text, 'answer', t.id, 'mama');
      }
    }
  }, [d.turns, voice]);

  // Keys: hold ⌥Space to talk, ⌥⇧Space for hands-free, ⌘. to repeat, Esc stops the voice first.
  useEffect(() => {
    let holding = false;
    const down = (e: KeyboardEvent) => {
      const v = voiceRef.current;
      if (e.code === 'Space' && e.altKey) {
        e.preventDefault();
        if (e.repeat) return;
        if (e.shiftKey) { v.toggleConversation(); return; }
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
  }, []);

  const onSendRb = useCallback((prompt: string) => {
    setReadback(rb => { if (rb) send(prompt, rb.callId); return null; });
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

  const orbState: OrbState = voice.error ? 'error' : readback ? 'confirming' : voice.mic !== 'idle' ? voice.mic
    : voice.speaking ? 'speaking' : d.live ? 'thinking' : voice.available === false ? 'error' : 'idle';

  const orb: ReactNode = (
    <>
      <Orb state={orbState} level={voice.level} conversation={voice.mode === 'conversation'}
        onHold={() => void voice.listen('push')} onRelease={() => void voice.release()} onTap={() => (voice.mic === 'idle' ? void voice.listen('tap') : voice.cancelListen())}
        onStop={voice.stopSpeaking} />
      <button type="button" className="convo-btn" aria-pressed={voice.mode === 'conversation'} onClick={voice.toggleConversation}
        title={voice.settings.engine === 'realtime' ? 'Hands-free with GPT live (⌥⇧Space)' : 'Hands-free conversation (⌥⇧Space)'}>
        {voice.settings.engine === 'realtime' ? 'GPT LIVE' : 'HANDS-FREE'}
      </button>
    </>
  );

  const above: ReactNode = (
    <>
      {voice.error && <div className="voice-toast" role="alert">{voice.error}</div>}
      {readback && <ReadBack rb={readback} onSend={onSendRb} onEdit={onEditRb} onCancel={onCancelRb} onPick={onPick} />}
      {!readback && voice.mic !== 'idle' && (voice.partial || voice.heard
        ? <Captions text={voice.partial || voice.heard} words={[]} clock={voice.clock} listening />
        : <Captions text="Listening… try “brief me on an account”, “previous answer” or “what can I say?”" words={[]} clock={voice.clock} listening />)}
      {!readback && voice.caption && voice.caption.text && <Captions text={voice.caption.text} words={voice.caption.words} clock={voice.clock} agent={voice.caption.agent} />}
    </>
  );

  const headerExtra: ReactNode = (
    <>
      {d.route !== 'chat' && (
        <span className="hdr-orb">
          <Orb state={orbState} level={voice.level} conversation={voice.mode === 'conversation'}
            onHold={() => void voice.listen('push')} onRelease={() => void voice.release()} onTap={() => (voice.mic === 'idle' ? void voice.listen('tap') : voice.cancelListen())}
            onStop={voice.stopSpeaking} />
        </span>
      )}
      {voice.mode === 'conversation' && (
        <button type="button" className="mic-on" onClick={voice.cancelListen} title="End hands-free mode">
          <i aria-hidden="true" />{voice.live ? 'GPT LIVE' : 'MIC ON'}
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

  const panel = useMemo(() => (settingsOpen ? <VoiceSettingsPanel voice={voice} onClose={() => setSettingsOpen(false)} /> : null), [settingsOpen, voice]);

  return { voice, orb, above, headerExtra, panel };
}
