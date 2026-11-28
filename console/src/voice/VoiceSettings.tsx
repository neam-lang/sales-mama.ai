// Voice settings (spec §15.4): who listens, who speaks, which voice, and GPT live.
// Providers without a key are shown with the file to put it in; keys are never typed here.
import { useEffect, useRef } from 'react';
import { PROVIDER_NAME, PROVIDERS, STYLE_PRESETS, type Provider, type VoiceOption } from '../../shared/voice';
import type { Voice } from './useVoice';

const LANGS: [string, string][] = [['en', 'English'], ['auto', 'Detect'], ['ms', 'Malay'], ['zh', 'Mandarin'], ['ta', 'Tamil'], ['hi', 'Hindi']];

function VoicePicker({ label, options, value, onChange }: { label: string; options: VoiceOption[]; value: string; onChange: (id: string) => void }) {
  const mine = options.filter(o => o.note === 'your custom voice');
  const male = options.filter(o => o.gender === 'male' && !mine.includes(o));
  const rest = options.filter(o => !mine.includes(o) && !male.includes(o));
  const has = options.some(o => o.id === value);
  const opt = (o: VoiceOption) => <option key={o.id} value={o.id}>{o.name}{o.note ? ` · ${o.note}` : ''}</option>;
  return (
    <label>{label}
      <select value={value} onChange={e => onChange(e.target.value)}>
        {!has && <option value={value}>{value}</option>}
        {mine.length > 0 && <optgroup label="Your voices">{mine.map(opt)}</optgroup>}
        {male.length > 0 && <optgroup label="Male">{male.map(opt)}</optgroup>}
        {rest.length > 0 && <optgroup label="Other">{rest.slice(0, 200).map(opt)}</optgroup>}
      </select>
    </label>
  );
}

export function VoiceSettingsPanel({ voice, onClose }: { voice: Voice; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const s = voice.settings;
  const prov = voice.providers;
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    const click = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node) && !(e.target as HTMLElement).closest('.voice-gear')) onClose(); };
    window.addEventListener('keydown', k);
    window.addEventListener('mousedown', click);
    return () => { window.removeEventListener('keydown', k); window.removeEventListener('mousedown', click); };
  }, [onClose]);
  const ok = (p: Provider) => !!prov?.[p]?.available;
  const missing = PROVIDERS.filter(p => prov && !prov[p].available);
  const realtime = s.engine === 'realtime';

  return (
    <div className="voice-settings" ref={ref} role="dialog" aria-label="Voice settings">
      <div className="vs-row"><b>Voice</b>
        <label className="vs-row"><input type="checkbox" checked={voice.speakAnswers} onChange={e => voice.setSpeakAnswers(e.target.checked)} /> Speak answers</label>
      </div>

      <label>Conversation engine
        <select value={s.engine} onChange={e => voice.setSettings({ engine: e.target.value as 'cascade' | 'realtime' })}>
          <option value="cascade">Sales Mama answers (speech in, speech out)</option>
          <option value="realtime" disabled={!ok('openai')}>GPT live: OpenAI Realtime, hands-free{ok('openai') ? '' : ' (needs OpenAI key)'}</option>
        </select>
      </label>
      {realtime && (
        <>
          <label className="vs-row">
            <input type="checkbox" checked={s.strict} onChange={e => voice.setSettings({ strict: e.target.checked })} />
            GPT only relays Sales Mama (recommended)
          </label>
          <VoicePicker label="GPT live voice" options={prov?.openai.voices.length ? [...(prov.openai.voices)] : []} value={s.voices.realtime}
            onChange={id => voice.setSettings({ voices: { ...s.voices, realtime: id } })} />
          <p className="vs-note">GPT live is used in hands-free mode. GPT never answers work questions itself: it asks Sales Mama and says the answer. Push-to-talk still uses the providers below.</p>
        </>
      )}

      <label>Listening (speech to text)
        <select value={s.stt} onChange={e => voice.setSettings({ stt: e.target.value as Provider })}>
          {PROVIDERS.map(p => <option key={p} value={p} disabled={!ok(p)}>{PROVIDER_NAME[p]}{ok(p) ? '' : ' (no key)'}</option>)}
        </select>
      </label>
      <label>Speaking (text to speech)
        <select value={s.tts} onChange={e => voice.setSettings({ tts: e.target.value as Provider })}>
          {PROVIDERS.map(p => <option key={p} value={p} disabled={!ok(p)}>{PROVIDER_NAME[p]}{ok(p) ? '' : ' (no key)'}</option>)}
        </select>
      </label>
      <VoicePicker label={`${PROVIDER_NAME[s.tts]} voice`} options={prov?.[s.tts]?.voices ?? []} value={s.voices[s.tts]}
        onChange={id => voice.setSettings({ voices: { ...s.voices, [s.tts]: id } })} />

      <label>Accent and delivery{s.tts === 'elevenlabs' ? ' (not used by ElevenLabs)' : ''}
        <select value={s.style} onChange={e => voice.setSettings({ style: e.target.value })}>
          {!STYLE_PRESETS.some(([v]) => v === s.style) && <option value={s.style}>{s.style}</option>}
          {STYLE_PRESETS.map(([v, n]) => <option key={n} value={v}>{n}</option>)}
        </select>
      </label>
      <label>Speed {s.rate.toFixed(2)}×
        <input type="range" min={0.8} max={1.3} step={0.05} value={s.rate} onChange={e => voice.setSettings({ rate: Number(e.target.value) })} />
      </label>
      <label>Language
        <select value={s.lang} onChange={e => voice.setSettings({ lang: e.target.value })}>
          {LANGS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
        </select>
      </label>

      <div className="vs-row">
        <button type="button" className="rb-btn" onClick={() => voice.say('Hi, this is Sales Mama. You have three meetings today, and two follow-ups are due.', 'notice')}>Preview voice</button>
        <button type="button" className="rb-btn" onClick={voice.resetSettings}>Use defaults</button>
      </div>
      {voice.problem && <p className="vs-problem">{voice.problem.message} {voice.problem.fix}</p>}
      {missing.length > 0 && <p className="vs-note">To add {missing.map(p => PROVIDER_NAME[p]).join(' or ')}, save the key to {missing.map(p => prov![p].keyFile).join(' or ')} as {'{"api_key": "…"}'} and restart the console.</p>}
      <p className="vs-note">Audio is streamed to the provider you pick and never stored. Answers stay on screen. Sending always needs your click in Claude Code.</p>
    </div>
  );
}
