// Voice keys and local defaults (voice spec §3.2, §15). Keys are typed by the person into
// ~/.config/sales-mama/<provider>.json (mode 600) or come from the environment. They never reach
// the browser and are never logged. Local defaults (for example your own cloned voice) live in
// ~/.config/sales-mama/voice.json, outside the repo, so a personal voice id is never committed.
import { existsSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { DEFAULT_SETTINGS, mergeSettings, type Provider, type VoiceSettings } from '../../shared/voice';

const DIR = () => process.env.MAMA_CONFIG_DIR ?? join(homedir(), '.config', 'sales-mama');
const ENV: Record<Provider, string> = { inworld: 'INWORLD_API_KEY', openai: 'OPENAI_API_KEY', elevenlabs: 'ELEVENLABS_API_KEY' };

export const keyFile = (p: Provider) => join(DIR(), `${p}.json`);

export function readKey(p: Provider): string | null {
  const env = process.env[ENV[p]]?.trim();
  if (env) return env;
  try {
    const f = keyFile(p);
    if (existsSync(f)) {
      const k = String(JSON.parse(readFileSync(f, 'utf8')).api_key ?? '').trim();
      if (k) return k;
    }
    // Also accept ~/.config/sales-mama/<provider>.env with a line like OPENAI_API_KEY=…
    const envFile = join(DIR(), `${p}.env`);
    if (existsSync(envFile)) {
      const line = readFileSync(envFile, 'utf8').split(/\r?\n/).find(l => l.trim().startsWith(`${ENV[p]}=`));
      const k = line?.slice(line.indexOf('=') + 1).trim().replace(/^["']|["']$/g, '');
      if (k) return k;
    }
    return null;
  } catch { return null; }
}

export function noKey(p: Provider) {
  const name = { inworld: 'Inworld', openai: 'OpenAI', elevenlabs: 'ElevenLabs' }[p];
  return {
    message: `${name} is not set up: no API key.`,
    fix: `Save it to ~/.config/sales-mama/${p}.json as {"api_key": "…"} (chmod 600), or set ${ENV[p]}, then restart the console.`,
  };
}

/** Defaults for this machine: DEFAULT_SETTINGS, then ~/.config/sales-mama/voice.json, then env. */
export function localDefaults(): VoiceSettings {
  let file: Partial<VoiceSettings> = {};
  try {
    const f = join(DIR(), 'voice.json');
    if (existsSync(f)) file = JSON.parse(readFileSync(f, 'utf8'));
  } catch { /* ignore a broken file */ }
  const s = mergeSettings(DEFAULT_SETTINGS, file);
  const env = process.env;
  const prov = (v: string | undefined) => (v === 'inworld' || v === 'openai' || v === 'elevenlabs' ? v : undefined);
  return {
    ...s,
    stt: prov(env.MAMA_VOICE_STT) ?? s.stt,
    tts: prov(env.MAMA_VOICE_TTS) ?? s.tts,
    engine: env.MAMA_VOICE_ENGINE === 'realtime' || env.MAMA_VOICE_ENGINE === 'cascade' ? env.MAMA_VOICE_ENGINE : s.engine,
  };
}

/** Untrusted settings from the browser → safe values. */
export function cleanSettings(base: VoiceSettings, s: any): VoiceSettings {
  const prov = (v: unknown, d: Provider): Provider => (v === 'inworld' || v === 'openai' || v === 'elevenlabs' ? v : d);
  const vid = (v: unknown, d: string) => (typeof v === 'string' && /^[\w.-]{1,120}$/.test(v) ? v : d);
  const voices = { ...base.voices };
  if (s?.voices && typeof s.voices === 'object') for (const k of Object.keys(voices) as (keyof typeof voices)[]) voices[k] = vid(s.voices[k], voices[k]);
  return {
    engine: s?.engine === 'realtime' || s?.engine === 'cascade' ? s.engine : base.engine,
    stt: prov(s?.stt, base.stt),
    tts: prov(s?.tts, base.tts),
    voices,
    rate: typeof s?.rate === 'number' && Number.isFinite(s.rate) ? Math.min(1.3, Math.max(0.8, s.rate)) : base.rate,
    lang: typeof s?.lang === 'string' && /^(auto|[a-z]{2}(-[A-Z]{2})?)$/.test(s.lang) ? s.lang : base.lang,
    strict: typeof s?.strict === 'boolean' ? s.strict : base.strict,
  };
}
