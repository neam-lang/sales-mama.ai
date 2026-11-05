import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { useBridge } from './useBridge';
import { TurnView } from './components/Turn';
import { Rail } from './components/Rail';
import { SourceDrawer } from './components/SourceDrawer';

const REP_SKILLS = ['/mama-day', '/mama-book', '/company-check', '/company-insights', '/mama-draft', '/mama-send', '/mama-replies'];
const MANAGER_SKILLS = ['/mama-manager', '/mama-allocate', '/company-check', '/company-insights', '/mama-weekly', '/mama-day'];

export function App() {
  const { turns, rail, connected, busy, replay, saved, ask, stop, newChat } = useBridge();
  const [draft, setDraft] = useState('');
  const [source, setSource] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const me = rail?.me;
  const manager = me?.role === 'manager';
  const skills = manager ? MANAGER_SKILLS : REP_SKILLS;
  const canAsk = connected && !busy;

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [turns]);

  const prompt = useCallback((text: string) => { if (canAsk) ask(text); }, [ask, canAsk]);
  const ctx = { onPrompt: prompt, onSource: setSource, disabled: !canAsk };

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!draft.trim() || !canAsk) return;
    ask(draft);
    setDraft('');
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); }
  };
  const pickSkill = (s: string) => { setDraft(s + ' '); inputRef.current?.focus(); };

  const window0 = rail?.windows[0];
  const initials = (me?.name || me?.id || '?').split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase();

  return (
    <>
      <header className="top">
        <div className="brand"><span className="logo" aria-hidden="true">SM</span>Sales Mama</div>
        <div className="top-right">
          <span className="pill status" role="status">{replay ? 'Replay · recorded stream' : saved ? 'Saved result' : !connected ? 'Reconnecting…' : busy ? 'Working…' : 'Ready'}</span>
          {window0 && <span className={`pill window${window0.open ? ' open' : ''}`}>{window0.market} · {window0.label}</span>}
          <button type="button" className="ghost" onClick={newChat} disabled={busy}>New chat</button>
          {me && <span className="avatar" title={`${me.name} · ${me.role}`} aria-label={`${me.name}, ${me.role}`}>{initials}</span>}
        </div>
      </header>

      <div className="shell">
        <main className="chat">
          {turns.length === 0 && (
            <div className="empty-state">
              <h1>{me ? `Morning, ${me.name.split(' ')[0]}.` : 'Sales Mama'}</h1>
              <p>{manager ? 'Start with your cockpit, check a company, or ask about the team.' : 'Run your day, check a company, or ask about your book.'}</p>
              <div className="quick" style={{ justifyContent: 'center' }}>
                {(manager ? ['/mama-manager', '/company-check', '/company-insights segment --industry clinics', 'What changed overnight?'] : ['/mama-day', '/company-check', '/mama-book', 'What changed overnight?'])
                  .map(q => <button key={q} type="button" disabled={!canAsk} onClick={() => prompt(q)}>{q}</button>)}
              </div>
            </div>
          )}
          {turns.map(t => <TurnView key={t.id} t={t} ctx={ctx} />)}
          <div ref={endRef} />

          <form className="composer" onSubmit={submit}>
            <div className="slash" aria-label="Skills">
              {skills.map(s => <button key={s} type="button" onClick={() => pickSkill(s)}>{s}</button>)}
            </div>
            <div className="compose-row">
              <label htmlFor="composer" className="sr">Ask Sales Mama</label>
              <textarea id="composer" ref={inputRef} rows={1} value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={onKey}
                placeholder={manager ? 'Approve, edit in a sentence, or ask about the team' : 'Ask anything, or type / for a skill'} />
              {busy && !replay && !saved
                ? <button type="button" className="go stop" aria-label="Stop the run" onClick={stop}>
                    <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16"><rect x="3" y="3" width="10" height="10" rx="2" fill="currentColor" /></svg>
                  </button>
                : <button type="submit" className="go" aria-label="Ask Sales Mama" disabled={!canAsk || !draft.trim()}>
                    <svg aria-hidden="true" width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M4 10h11M10 5l5 5-5 5" /></svg>
                  </button>}
            </div>
          </form>
        </main>
        <Rail rail={rail} onSource={setSource} onPrompt={prompt} disabled={!canAsk} />
      </div>
      {source && <SourceDrawer path={source} onClose={() => setSource(null)} />}
    </>
  );
}
