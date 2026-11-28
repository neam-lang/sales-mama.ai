// The app shell (spec §3–5): ink header with market clocks, search and the pulse bar, a slim nav
// rail, the routed main pane and the context panel. The document never scrolls; each pane owns its
// scroll. Every button anywhere is a prompt (ADR-0006).
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { AccountInfo, SkillInfo } from '../server/repo';
import { useBridge } from './useBridge';
import { useRoute, type Route } from './app/router';
import { useTheme } from './hooks/useTheme';
import { useHotkeys } from './hooks/useHotkeys';
import { Header, type PulseLane } from './app/Header';
import { NavRail, TabBar } from './app/Nav';
import { ChatView } from './app/ChatView';
import { TodayView } from './app/TodayView';
import { BookView } from './app/BookView';
import { IconAuto, IconBook, IconBolt, IconCalendar, IconChat, IconFire, IconPlus, IconReports, IconToday } from './app/Icons';
import { Rail } from './components/Rail';
import { SourceDrawer } from './components/SourceDrawer';
import { CommandPalette, ShortcutSheet, type PaletteItem } from './palette/CommandPalette';
import { loadChats, useSaveChat, type SavedChat } from './chat/history';
import { useCalendar } from './calendar/useCalendar';
import { CalendarView } from './calendar/CalendarView';
import { NextUpCapsule } from './calendar/NextUp';
import { useReminders } from './calendar/reminders';
import type { CalItem } from './calendar/time';
import { useNow } from './hooks/useNow';
import { Canvas, useCanvasWidth, type CanvasContent } from './canvas/Canvas';
import { ReportsView } from './reports/ReportsView';
import { followUpsFor } from './chat/followups';
import { useVoiceController } from './voice/useVoiceController';

function useCatalog(connected: boolean) {
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  useEffect(() => {
    if (!connected) return;
    fetch('/api/skills').then(r => r.json()).then(setSkills).catch(() => {});
    fetch('/api/accounts').then(r => r.json()).then(setAccounts).catch(() => {});
  }, [connected]);
  return { skills, accounts };
}

export function App() {
  const { turns, rail, connected, busy, replay, replaying, saved, sessionId, chatId, ask, stop, newChat, loadChat } = useBridge();
  const { route, go } = useRoute();
  const { theme, cycle } = useTheme();
  const { skills, accounts } = useCatalog(connected);
  const [source, setSource] = useState<string | null>(null);
  const [seed, setSeed] = useState<string | null>(null);
  const [queued, setQueued] = useState<string | null>(null);
  const [palette, setPalette] = useState(false);
  const [help, setHelp] = useState(false);
  const [focus, setFocus] = useState<string | null>(null);
  const [canvas, setCanvas] = useState<CanvasContent | null>(null);
  const [canvasW, setCanvasW] = useCanvasWidth();
  const cal = useCalendar(rail);
  const reminders = useReminders(cal.mine);
  const now = useNow(30_000);
  const me = rail?.me;
  const manager = me?.role === 'manager';
  const canAsk = connected && !busy;
  const live = (busy && !replay && !saved) || replaying;

  useSaveChat(chatId, turns, sessionId, !replay && !saved);

  const askAndShow = useCallback((text: string) => {
    if (!canAsk || !text.trim()) return;
    ask(text);
    go('chat');
  }, [ask, canAsk, go]);
  const openCanvas = useCallback((part: CanvasContent['parts'][number]) => {
    setCanvas({ key: `${part.block.surfaceId}-${Date.now()}`, title: part.block.title ?? part.block.surfaceId.replace(/_/g, ' '), parts: [part], source: part.block.dataRef });
  }, []);
  const ctx = useMemo(() => ({ onPrompt: askAndShow, onSource: setSource, disabled: !canAsk, openCanvas }), [askAndShow, canAsk, openCanvas]);

  // A prompt typed during a run is sent as soon as the run ends.
  useEffect(() => {
    if (queued && canAsk) { ask(queued); setQueued(null); }
  }, [queued, canAsk, ask]);

  const lanes: PulseLane[] = useMemo(() => {
    const running = turns.find(t => t.running);
    return (running?.turn.lanes ?? []).map(l => ({ id: l.id, agent: l.agent.toLowerCase(), running: l.status === 'running' }));
  }, [turns]);

  const status = replay ? (replaying ? 'Replaying…' : 'Replay') : saved ? 'Saved result' : !connected ? 'Reconnecting…' : live ? 'Working…' : 'Ready';
  const showCanvas = !!canvas && (route === 'chat' || route === 'book' || route === 'reports');
  const onNewChat = useCallback(() => { newChat(); setQueued(null); go('chat'); }, [newChat, go]);
  const prefill = useCallback((text: string) => { go('chat'); setSeed(text); }, [go]);
  const openChat = useCallback((c: SavedChat) => { if (!busy) { loadChat(c); go('chat'); } }, [busy, loadChat, go]);
  const openEvent = useCallback((i: CalItem) => { setFocus(i.id); go('calendar'); }, [go]);
  // Voice (Sales-Mama-Voice-design-spec.md): speech becomes the same prompts as typed text.
  const followUps = useMemo(() => followUpsFor(turns[turns.length - 1]), [turns]);
  const openRecent = useCallback(() => { const c = loadChats()[0]; if (!c || busy) return false; openChat(c); return true; }, [busy, openChat]);
  const vc = useVoiceController({ turns, accounts, canAsk, live, followUps, route, ask, stop, go, newChat: onNewChat, queue: setQueued, edit: prefill,
    openRecent, openPalette: () => setPalette(true), showHelp: () => setHelp(true) });

  useHotkeys({
    palette: () => setPalette(p => !p),
    slash: () => prefill('/'),
    jump: () => { go('chat'); window.dispatchEvent(new Event('mama:jump')); },
    help: () => setHelp(true),
    go: k => go(({ t: 'today', c: 'chat', k: 'calendar', b: 'book', r: 'reports' } as Record<string, Route>)[k]),
  });

  const paletteItems = useMemo<PaletteItem[]>(() => {
    if (!palette) return [];
    const items: PaletteItem[] = [
      { id: 'new', group: 'Actions', label: 'New chat', icon: <IconPlus size={16} />, run: onNewChat },
      { id: 'theme', group: 'Actions', label: `Switch theme (now ${theme})`, icon: <IconAuto size={16} />, run: cycle },
      { id: 'keys', group: 'Actions', label: 'Keyboard shortcuts', keys: '?', icon: <IconBolt size={16} />, run: () => setHelp(true) },
      { id: 'go-today', group: 'Go to', label: 'Today', keys: 'g t', icon: <IconToday size={16} />, run: () => go('today') },
      { id: 'go-chat', group: 'Go to', label: 'Chat', keys: 'g c', icon: <IconChat size={16} />, run: () => go('chat') },
      { id: 'go-cal', group: 'Go to', label: 'Calendar', keys: 'g k', icon: <IconCalendar size={16} />, run: () => go('calendar') },
      { id: 'go-book', group: 'Go to', label: 'Book', keys: 'g b', icon: <IconBook size={16} />, run: () => go('book') },
      { id: 'go-reports', group: 'Go to', label: 'Reports', keys: 'g r', icon: <IconReports size={16} />, run: () => go('reports') },
    ];
    for (const s of skills) {
      if (!manager && s.role === 'manager') continue;
      items.push({ id: `skill-${s.name}`, group: 'Skills', label: `/${s.name}`, hint: s.description, icon: <span className="pal-slash">/</span>, run: () => prefill(`/${s.name} `) });
    }
    for (const a of accounts) {
      items.push({ id: `acc-${a.id}`, group: 'Accounts', label: a.name || a.id, hint: `${a.market} · tier ${a.tier || '–'} · ${a.stage || 'new'} · brief me`,
        icon: <IconFire size={16} />, run: () => prefill(`/mama-brief ${a.id}`) });
    }
    for (const c of loadChats()) {
      items.push({ id: `chat-${c.id}`, group: 'Recent chats', label: c.title, hint: new Date(c.updated).toLocaleString(), icon: <IconChat size={16} />, run: () => openChat(c) });
    }
    return items;
  }, [palette, skills, accounts, manager, theme, cycle, go, onNewChat, prefill, openChat]);

  return (
    <div className="app">
      <Header rail={rail} status={status} live={live} theme={theme} onTheme={cycle} onNewChat={onNewChat} newChatDisabled={busy} lanes={lanes}
        onSearch={() => setPalette(true)} nextUp={<NextUpCapsule cal={cal.mine} now={now} onOpen={openEvent} />} extra={vc.headerExtra} />
      {vc.panel}
      <div className={`body r-${route}${showCanvas ? ' with-canvas' : ''}`} style={showCanvas ? { ['--panel-w' as any]: `${canvasW}px` } : undefined}>
        <NavRail route={route} go={go} busy={live} />
        <main className="main" id="main">
          {route === 'today' && <TodayView rail={rail} canAsk={canAsk} live={live} ask={askAndShow} stop={stop} openSource={setSource} skills={skills} accounts={accounts} cal={cal.mine} openEvent={openEvent} />}
          {route === 'calendar' && <CalendarView mine={cal.mine} team={cal.team} manager={manager} error={cal.error} focus={focus} onFocused={() => setFocus(null)}
            reminders={reminders} act={{ ask: askAndShow, prefill, openSource: setSource, disabled: !canAsk }} />}
          {/* Chat stays mounted so its scroll position and draft survive a trip to Today or Book. */}
          <div className="route-chat" hidden={route !== 'chat'}>
            <ChatView turns={turns} ctx={ctx} manager={manager} firstName={me?.name.split(' ')[0] ?? ''} canAsk={canAsk} live={live}
              ask={ask} stop={stop} seed={seed} onSeedUsed={() => setSeed(null)} skills={skills} accounts={accounts}
              queued={queued} onQueue={setQueued} onCancelQueue={() => setQueued(null)} onOpenChat={openChat}
              voiceSlot={vc.orb} voiceAbove={vc.above} />
          </div>
          {route === 'book' && <BookView rail={rail} ctx={ctx} />}
          {route === 'reports' && <ReportsView onOpen={setCanvas} current={canvas?.source} />}
        </main>
        {showCanvas && canvas
          ? <Canvas content={canvas} width={canvasW} onWidth={setCanvasW} onClose={() => setCanvas(null)} ctx={ctx} />
          : (route === 'chat' || route === 'book') && <Rail rail={rail} onSource={setSource} onPrompt={askAndShow} disabled={!canAsk} />}
      </div>
      <TabBar route={route} go={go} busy={live} />
      <CommandPalette open={palette} onClose={() => setPalette(false)} items={paletteItems} />
      <ShortcutSheet open={help} onClose={() => setHelp(false)} />
      {source && <SourceDrawer path={source} onClose={() => setSource(null)} />}
    </div>
  );
}
