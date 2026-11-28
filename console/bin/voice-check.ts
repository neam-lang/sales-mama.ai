// npm run voice:check: checks each voice provider you have a key for, against the real API.
// Speaks one short sentence, transcribes it back, and (OpenAI) opens a GPT live session to check that
// GPT calls ask_sales_mama instead of answering. Costs a few cents. Prints timings; never prints keys.
import WebSocket from 'ws';
import { readKey } from '../server/voice/config';
import { OpenAiTts, openAiTranscribe, OPENAI_MODELS, realtimeInstructions, REALTIME_TOOLS } from '../server/voice/openai';
import { ElevenTts, elevenTranscribe } from '../server/voice/elevenlabs';
import { SttSession, Tts } from '../server/voice/inworld';
import { Resampler, toInt16, fromInt16, wav } from '../server/voice/pcm';
import { localDefaults } from '../server/voice/config';
import type { TtsEngine } from '../server/voice/types';
import type { Provider } from '../shared/voice';

const SENTENCE = 'You have three meetings today. Next is Kestrel Physio at two pm.';
const s = localDefaults();

async function speak(name: string, tts: TtsEngine, voiceId: string): Promise<Buffer | null> {
  const t0 = Date.now();
  let first = 0;
  const parts: Buffer[] = [];
  let words = 0;
  return new Promise(res => tts.speak(`check-${name}`, SENTENCE, { voiceId, rate: 1, lang: 'en' }, {
    audio: b => { if (!first) first = Date.now() - t0; parts.push(b); },
    words: w => { words += w.length; },
    end: (ok, e) => {
      const pcm = Buffer.concat(parts);
      console.log(`  TTS ${ok ? 'ok ' : 'FAIL'} voice ${voiceId}: first audio ${first} ms, ${(pcm.length / 48000).toFixed(1)} s audio, ${words} word timings${e ? ` (${e})` : ''}`);
      tts.close();
      res(ok ? pcm : null);
    },
  }));
}

function to16k(pcm24: Buffer): Buffer { return fromInt16(new Resampler(24000, 16000).push(toInt16(pcm24))); }

async function main() {
  for (const p of ['inworld', 'openai', 'elevenlabs'] as Provider[]) {
    const key = readKey(p);
    console.log(`\n${p}: ${key ? 'key found' : 'no key (skipped)'}`);
    if (!key) continue;
    const tts = p === 'inworld' ? new Tts(key) : p === 'openai' ? new OpenAiTts(key) : new ElevenTts(key);
    const pcm = await speak(p, tts, s.voices[p]);
    if (!pcm) continue;
    const pcm16 = to16k(pcm);
    const t0 = Date.now();
    try {
      let text = '';
      if (p === 'inworld') {
        text = await new Promise<string>((res, rej) => {
          const st = new SttSession(key, 'push', { lang: 'en', prompts: ['Kestrel Physio'] }, { started() {}, partial() {}, final: res, nothing: () => res(''), error: rej });
          for (let i = 0; i < pcm16.length; i += 3200) st.push(pcm16.subarray(i, i + 3200));
          st.finish();
        });
      } else {
        text = await (p === 'openai' ? openAiTranscribe(key) : elevenTranscribe(key))(wav(pcm16, 16000), { lang: 'en', prompts: ['Kestrel Physio'] }, new AbortController().signal);
      }
      console.log(`  STT ok   ${Date.now() - t0} ms: "${text}"`);
    } catch (e) { console.log(`  STT FAIL ${(e as Error).message}`); }

    if (p === 'openai') await realtime(key);
  }
}

function realtime(key: string): Promise<void> {
  return new Promise(res => {
    const t0 = Date.now();
    const ws = new WebSocket(`wss://api.openai.com/v1/realtime?model=${encodeURIComponent(OPENAI_MODELS.realtime)}`, { headers: { Authorization: `Bearer ${key}` } });
    let finished = false;
    const done = (msg: string) => { if (finished) return; finished = true; console.log(`  GPT live ${msg}`); clearTimeout(timer); ws.close(); res(); };
    const timer = setTimeout(() => done('FAIL: timed out'), 20000);
    ws.on('unexpected-response', (_q, r) => done(`FAIL: HTTP ${r.statusCode}`));
    ws.on('error', e => done(`FAIL: ${e.message}`));
    ws.on('open', () => ws.send(JSON.stringify({
      type: 'session.update', session: {
        type: 'realtime', model: OPENAI_MODELS.realtime, instructions: realtimeInstructions(true), output_modalities: ['audio'],
        audio: {
          input: { format: { type: 'audio/pcm', rate: 24000 }, noise_reduction: { type: 'near_field' }, transcription: { model: OPENAI_MODELS.stt, language: 'en' },
            turn_detection: { type: 'semantic_vad', eagerness: 'auto', create_response: true, interrupt_response: true } },
          output: { format: { type: 'audio/pcm', rate: 24000 }, voice: s.voices.realtime, speed: 1 },
        },
        tools: REALTIME_TOOLS, tool_choice: 'required',
      },
    })));
    let asked = false;
    ws.on('message', d => {
      const e = JSON.parse(String(d));
      if (e.type === 'session.updated' && !asked) {
        asked = true;
        const ss = e.session;
        console.log(`  GPT live session ok in ${Date.now() - t0} ms: model ${ss.model}, voice ${ss.audio?.output?.voice}, tools ${ss.tools?.map((t: { name: string }) => t.name).join('+')}, tool_choice ${ss.tool_choice}`);
        ws.send(JSON.stringify({ type: 'conversation.item.create', item: { type: 'message', role: 'user', content: [{ type: 'input_text', text: 'How many meetings do I have today?' }] } }));
        ws.send(JSON.stringify({ type: 'response.create' }));
      }
      if (e.type === 'response.output_item.done' && e.item?.type === 'function_call') done(`relay ok: GPT called ${e.item.name}(${e.item.arguments}) instead of answering`.replace(/\s+/g, ' '));
      if (e.type === 'response.done' && asked) done(`FAIL: GPT answered without calling Sales Mama (status ${e.response?.status})`);
      if (e.type === 'error') console.log(`  GPT live error: ${e.error?.message}`);
    });
  });
}

await main();
