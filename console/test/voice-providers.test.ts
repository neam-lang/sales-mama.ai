// Configurable providers (voice spec §15) against mock OpenAI and ElevenLabs servers: TTS streaming,
// batch STT with the endpointer, and OpenAI Realtime ("GPT live") as a relay to Sales Mama, with the
// grounding guard. Plus the pure PCM helpers. No keys, no network.
import { createServer, type IncomingMessage, type Server } from 'node:http';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import WebSocket, { WebSocketServer } from 'ws';
import { numbersIn, toolCommand, ungroundedNumbers, type VoiceServerMsg } from '../shared/voice';
import { charsToWords, Endpointer, jsonObjects, PcmAligner, Resampler, wav } from '../server/voice/pcm';
import { realtimeInstructions, REALTIME_TOOLS } from '../server/voice/openai';

// ---------------------------------------------------------------------------------------------
describe('pcm helpers', () => {
  it('resamples 16 kHz to 24 kHz across chunk boundaries without clicks', () => {
    const r = new Resampler(16000, 24000);
    const ramp = Int16Array.from({ length: 3200 }, (_, i) => i);
    const out = [...r.push(ramp.subarray(0, 1600)), ...r.push(ramp.subarray(1600))];
    expect(out.length).toBeGreaterThanOrEqual(4798);
    expect(out.length).toBeLessThanOrEqual(4800);
    for (let i = 1; i < out.length; i++) expect(Math.abs(out[i] - out[i - 1])).toBeLessThanOrEqual(1);   // smooth ramp
  });
  it('keeps chunks sample-aligned', () => {
    const a = new PcmAligner();
    const sizes = [3, 5, 1, 7].map(n => a.push(Buffer.alloc(n)).length);
    expect(sizes.every(n => n % 2 === 0)).toBe(true);
    expect(sizes.reduce((x, y) => x + y)).toBe(16);
  });
  it('writes a valid WAV header', () => {
    const w = wav(Buffer.alloc(320), 16000);
    expect(w.subarray(0, 4).toString()).toBe('RIFF');
    expect(w.readUInt32LE(24)).toBe(16000);
    expect(w.readUInt32LE(40)).toBe(320);
  });
  it('splits streamed JSON objects, including ones cut mid-way', () => {
    const a = jsonObjects('{"a":1}\n{"b":"x}y"}{"c":');
    expect(a.objects).toEqual([{ a: 1 }, { b: 'x}y' }]);
    expect(jsonObjects(a.rest + '3}').objects).toEqual([{ c: 3 }]);
  });
  it('turns character timings into words', () => {
    expect(charsToWords([...'Hi you'], [0, .1, .2, .3, .4, .5], [.1, .2, .3, .4, .5, .6], 1))
      .toEqual([{ w: 'Hi', start: 1, end: 1.2 }, { w: 'you', start: 1.3, end: 1.6 }]);
  });
  it('endpointer: finds speech start and end in a tone between silences', () => {
    const ev: string[] = [];
    const ep = new Endpointer(16000, 600, () => ev.push('start'), () => ev.push('end'));
    ep.push(new Int16Array(16000 * 0.5));                 // silence
    ep.push(tone(0.6));
    expect(ev).toEqual(['start']);
    ep.push(new Int16Array(16000 * 1));
    expect(ev).toEqual(['start', 'end']);
  });
});

describe('grounding guard (GPT live)', () => {
  it('reads digits and number words', () => {
    expect(numbersIn('You have three meetings, 2 follow-ups and twenty five leads; S$12,400.')).toEqual([2, 12400, 3, 25]);
    expect(numbersIn('the one you mean')).toEqual([]);
  });
  it('flags numbers GPT said that Sales Mama did not', () => {
    expect(ungroundedNumbers('You have three meetings today.', 'You have 3 meetings today.')).toEqual([]);
    expect(ungroundedNumbers('You have five meetings today.', 'You have 3 meetings today.')).toEqual([5]);
    expect(ungroundedNumbers('Next is Kestrel at two pm.', 'Next is Kestrel at 14:00.')).toEqual([]);
  });
  it('maps tool commands to the keyboard verbs', () => {
    expect(toolCommand('open_calendar')).toEqual({ kind: 'go', route: 'calendar' });
    expect(toolCommand('pick_2')).toEqual({ kind: 'pick', index: 1 });
    expect(toolCommand('rm -rf')).toBeNull();
  });
  it('instructions keep GPT as the voice, not the brain', () => {
    const s = realtimeInstructions(true);
    expect(s).toMatch(/call ask_sales_mama/);
    expect(s).toMatch(/word for word/);
    expect(s).toMatch(/never send, approve or assign/);
    expect(s).toMatch(/Do not make small talk/);
    expect(REALTIME_TOOLS.map(t => t.name)).toEqual(['ask_sales_mama', 'voice_command']);
  });
});

// ---------------------------------------------------------------------------------------------
function tone(seconds: number, amp = 0.3): Int16Array {
  return Int16Array.from({ length: Math.round(16000 * seconds) }, (_, i) => Math.round(Math.sin((2 * Math.PI * 220 * i) / 16000) * amp * 32767));
}
const toBuf = (a: Int16Array) => Buffer.from(a.buffer, a.byteOffset, a.byteLength);

const seen = { speech: [] as any[], stt: [] as { model: string; hasWav: boolean; auth: string }[], eleven: [] as any[], rt: [] as any[], rtAuth: '' };
let mock: Server, bridge: Server, port = 0;
let rtSocket: WebSocket | null = null;

const body = (req: IncomingMessage) => new Promise<Buffer>(r => { const c: Buffer[] = []; req.on('data', d => c.push(d)); req.on('end', () => r(Buffer.concat(c))); });

beforeAll(async () => {
  mock = createServer(async (req, res) => {
    const url = req.url ?? '';
    const b = await body(req);
    if (url === '/v1/audio/speech') {                          // OpenAI TTS: chunked PCM with odd chunk sizes
      seen.speech.push({ ...JSON.parse(b.toString()), auth: req.headers.authorization });
      res.writeHead(200, { 'content-type': 'application/octet-stream' });
      res.write(Buffer.alloc(4801, 2));
      setTimeout(() => { res.end(Buffer.alloc(4799, 2)); }, 20);
      return;
    }
    if (url === '/v1/audio/transcriptions') {
      const t = b.toString('latin1');
      seen.stt.push({ model: /gpt-4o-mini-transcribe/.test(t) ? 'gpt-4o-mini-transcribe' : '?', hasWav: t.includes('RIFF'), auth: String(req.headers.authorization) });
      res.writeHead(200, { 'content-type': 'application/json' }).end(JSON.stringify({ text: 'Brief me on Kestrel Physio.' }));
      return;
    }
    if (url.startsWith('/v1/text-to-speech/')) {              // ElevenLabs TTS with timestamps
      seen.eleven.push({ url, key: req.headers['xi-api-key'], ...JSON.parse(b.toString()) });
      res.writeHead(200, { 'content-type': 'application/json' });
      const a = Buffer.alloc(4800, 3).toString('base64');
      const one = JSON.stringify({ audio_base64: a, alignment: { characters: [...'You have'], character_start_times_seconds: [0, .02, .04, .06, .08, .1, .12, .14], character_end_times_seconds: [.02, .04, .06, .08, .1, .12, .14, .16] } });
      const two = JSON.stringify({ audio_base64: a, alignment: { characters: [...' three.'], character_start_times_seconds: [.16, .18, .2, .22, .24, .26, .28], character_end_times_seconds: [.18, .2, .22, .24, .26, .28, .3] } });
      res.write(one + '\n' + two.slice(0, 30));
      setTimeout(() => res.end(two.slice(30) + '\n'), 20);
      return;
    }
    if (url === '/v1/speech-to-text') {
      const t = b.toString('latin1');
      seen.stt.push({ model: /scribe_v1/.test(t) ? 'scribe_v1' : '?', hasWav: t.includes('RIFF'), auth: String(req.headers['xi-api-key']) });
      res.writeHead(200, { 'content-type': 'application/json' }).end(JSON.stringify({ text: 'Check cinder coffee roasters' }));
      return;
    }
    if (url === '/v1/voices') {
      res.writeHead(200, { 'content-type': 'application/json' }).end(JSON.stringify({ voices: [{ voice_id: 'JBFqnCBsd6RMkjVDRZzb', name: 'George', labels: { gender: 'male', accent: 'british' } }] }));
      return;
    }
    res.writeHead(404).end();
  });
  const rtw = new WebSocketServer({ server: mock });
  rtw.on('connection', (ws, req) => {
    seen.rtAuth = String(req.headers.authorization);
    rtSocket = ws;
    ws.on('message', d => seen.rt.push(JSON.parse(String(d))));
  });
  await new Promise<void>(r => mock.listen(0, '127.0.0.1', () => r()));
  const mp = (mock.address() as { port: number }).port;
  Object.assign(process.env, {
    MAMA_OPENAI_HTTP: `http://127.0.0.1:${mp}`, MAMA_OPENAI_WS: `ws://127.0.0.1:${mp}`, MAMA_ELEVENLABS_HTTP: `http://127.0.0.1:${mp}`,
    OPENAI_API_KEY: 'sk-test', ELEVENLABS_API_KEY: 'xi-test', MAMA_VOICE_PREWARM: 'off',
    MAMA_CONFIG_DIR: mkdtempSync(join(tmpdir(), 'mama-voice-config-')), MAMA_VOICE_CACHE: mkdtempSync(join(tmpdir(), 'mama-voice-cache-')),
  });
  delete process.env.INWORLD_API_KEY;

  const { voiceSession } = await import('../server/voice/bridge');
  bridge = createServer();
  new WebSocketServer({ server: bridge }).on('connection', ws => voiceSession(ws, { accounts: () => [{ id: 'cinder-coffee-roasters', name: 'Cinder Coffee Roasters Pte Ltd' }] }));
  await new Promise<void>(r => bridge.listen(0, '127.0.0.1', () => r()));
  port = (bridge.address() as { port: number }).port;
});
afterAll(() => { mock.close(); bridge.close(); });

function client() {
  const ws = new WebSocket(`ws://127.0.0.1:${port}`);
  const msgs: VoiceServerMsg[] = [];
  const audio: Buffer[] = [];
  ws.on('message', (d, bin) => (bin ? audio.push(d as Buffer) : msgs.push(JSON.parse(String(d)))));
  const until = async (pred: () => boolean, ms = 3000) => {
    const t = Date.now();
    while (!pred()) { if (Date.now() - t > ms) throw new Error(`timeout; got ${JSON.stringify(msgs.map(m => m.type))}`); await new Promise(r => setTimeout(r, 10)); }
  };
  const open = new Promise<void>(r => ws.on('open', () => r()));
  return { ws, msgs, audio, until, open, send: (o: object) => ws.send(JSON.stringify(o)), of: <T extends VoiceServerMsg['type']>(t: T) => msgs.filter(m => m.type === t) as Extract<VoiceServerMsg, { type: T }>[] };
}

describe('OpenAI and ElevenLabs as providers (mock)', () => {
  it('reports which providers have keys; Inworld missing is explained', async () => {
    const c = client(); await c.open;
    await c.until(() => c.of('ready').length > 0);
    const r = c.of('ready')[0];
    expect(r.providers.openai.available).toBe(true);
    expect(r.providers.elevenlabs.available).toBe(true);
    expect(r.providers.inworld.available).toBe(false);
    expect(r.providers.elevenlabs.voices[0]).toMatchObject({ id: 'JBFqnCBsd6RMkjVDRZzb', gender: 'male' });
    expect(r.providers.openai.realtime).toBe(true);
    expect(JSON.stringify(r)).not.toMatch(/sk-test|xi-test/);
    c.ws.close();
  });

  it('OpenAI TTS: male voice, PCM, every chunk sample-aligned', async () => {
    const c = client(); await c.open;
    c.send({ type: 'settings', settings: { tts: 'openai' } });
    c.send({ type: 'speak', id: 'o1', text: 'You have three meetings today.' });
    await c.until(() => c.of('speech_end').length > 0);
    expect(seen.speech[0]).toMatchObject({ model: 'gpt-4o-mini-tts', voice: 'onyx', response_format: 'pcm', auth: 'Bearer sk-test' });
    expect(c.audio.every(b => b.length % 2 === 0)).toBe(true);
    expect(c.audio.reduce((n, b) => n + b.length, 0)).toBe(9600);
    c.ws.close();
  });

  it('ElevenLabs TTS: male voice, words from character timings across split chunks', async () => {
    const c = client(); await c.open;
    c.send({ type: 'settings', settings: { tts: 'elevenlabs' } });
    c.send({ type: 'speak', id: 'e1', text: 'You have three.' });
    await c.until(() => c.of('speech_end').length > 0);
    expect(seen.eleven[0].url).toBe('/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb/stream/with-timestamps?output_format=pcm_24000');
    expect(seen.eleven[0]).toMatchObject({ key: 'xi-test', model_id: 'eleven_flash_v2_5' });
    expect(c.of('words').flatMap(m => m.words).map(w => w.w)).toEqual(['You', 'have', 'three.']);
    expect(c.audio.reduce((n, b) => n + b.length, 0)).toBe(9600);
    c.ws.close();
  });

  it('OpenAI STT push-to-talk: WAV upload on release, one final', async () => {
    const c = client(); await c.open;
    c.send({ type: 'settings', settings: { stt: 'openai' } });
    c.send({ type: 'listen', mode: 'push' });
    for (let i = 0; i < 8; i++) c.ws.send(toBuf(tone(0.1)));
    c.send({ type: 'listen_end' });
    await c.until(() => c.of('final').length > 0);
    expect(c.of('final')[0].text).toBe('Brief me on Kestrel Physio.');
    expect(seen.stt.find(s => s.model === 'gpt-4o-mini-transcribe')).toMatchObject({ hasWav: true, auth: 'Bearer sk-test' });
    c.ws.close();
  });

  it('ElevenLabs STT tap-to-talk: the endpointer ends the turn by itself', async () => {
    const c = client(); await c.open;
    c.send({ type: 'settings', settings: { stt: 'elevenlabs' } });
    c.send({ type: 'listen', mode: 'tap' });
    c.ws.send(toBuf(new Int16Array(8000)));
    for (let i = 0; i < 6; i++) c.ws.send(toBuf(tone(0.1)));
    for (let i = 0; i < 12; i++) c.ws.send(toBuf(new Int16Array(1600)));
    await c.until(() => c.of('final').length > 0);
    expect(c.of('speech_started').length).toBe(1);
    expect(c.of('final')[0].text).toBe('Check cinder coffee roasters');
    expect(seen.stt.find(s => s.model === 'scribe_v1')).toMatchObject({ hasWav: true, auth: 'xi-test' });
    c.ws.close();
  });
});

describe('GPT live (OpenAI Realtime) relays to Sales Mama (mock)', () => {
  it('runs a full turn: tool call → prompt → answer said by GPT → grounding check', async () => {
    const c = client(); await c.open;
    c.send({ type: 'settings', settings: { engine: 'realtime' } });
    c.send({ type: 'listen', mode: 'conversation' });
    await c.until(() => c.of('live').some(m => m.on) && !!rtSocket && seen.rt.some(e => e.type === 'session.update'));
    const rt = rtSocket!;
    const emit = (e: object) => rt.send(JSON.stringify(e));

    // Session: strict relay, male voice, two tools, 24 kHz PCM both ways.
    const su = seen.rt.find(e => e.type === 'session.update').session;
    expect(seen.rtAuth).toBe('Bearer sk-test');
    expect(su).toMatchObject({ type: 'realtime', tool_choice: 'required', audio: { output: { voice: 'cedar', format: { type: 'audio/pcm', rate: 24000 } }, input: { format: { rate: 24000 } } } });
    expect(su.tools.map((t: any) => t.name)).toEqual(['ask_sales_mama', 'voice_command']);

    // Mic audio is resampled 16 → 24 kHz.
    c.ws.send(toBuf(tone(0.1)));
    await c.until(() => seen.rt.some(e => e.type === 'input_audio_buffer.append'));
    const append = seen.rt.find(e => e.type === 'input_audio_buffer.append');
    expect(Buffer.from(append.audio, 'base64').length).toBeGreaterThanOrEqual(4796);

    // GPT hears the user and calls Sales Mama; the browser gets a prompt (never an answer from GPT).
    emit({ type: 'input_audio_buffer.speech_started' });
    emit({ type: 'conversation.item.input_audio_transcription.completed', transcript: 'how many meetings today' });
    emit({ type: 'response.output_item.done', item: { type: 'function_call', name: 'ask_sales_mama', call_id: 'call_1', arguments: '{"request":"How many meetings do I have today?"}' } });
    await c.until(() => c.of('tool_prompt').length > 0);
    expect(c.of('heard')[0].text).toBe('how many meetings today');
    expect(c.of('tool_prompt')[0]).toEqual({ type: 'tool_prompt', callId: 'call_1', prompt: 'How many meetings do I have today?' });

    // Sales Mama answers; GPT is told to say it word for word, with no tools.
    c.send({ type: 'tool_result', callId: 'call_1', text: 'You have **3** meetings today. See `wiki/books/praveen.json`.' });
    await c.until(() => seen.rt.some(e => e.type === 'response.create'));
    const out = seen.rt.find(e => e.type === 'conversation.item.create' && e.item.type === 'function_call_output');
    expect(JSON.parse(out.item.output)).toEqual({ say: 'You have 3 meetings today. See.' });
    expect(seen.rt.find(e => e.type === 'response.create').response.tool_choice).toBe('none');

    // GPT speaks, but says the wrong number: the browser is warned.
    emit({ type: 'response.output_audio.delta', response_id: 'r1', delta: Buffer.alloc(4800, 1).toString('base64') });
    emit({ type: 'response.output_audio_transcript.delta', response_id: 'r1', delta: 'You have five meetings today.' });
    emit({ type: 'response.output_audio_transcript.done', response_id: 'r1', transcript: 'You have five meetings today.' });
    emit({ type: 'response.done', response: { id: 'r1', status: 'completed' } });
    await c.until(() => c.of('speech_end').length > 0 && c.of('mismatch').length > 0);
    expect(c.of('speech_begin')[0].id).toBe('r1');
    expect(c.of('speech_text').pop()!.text).toBe('You have five meetings today.');
    expect(c.audio.reduce((n, b) => n + b.length, 0)).toBe(4800);
    expect(c.of('mismatch')[0].source).toBe('You have 3 meetings today. See.');

    // Voice commands come back as commands, acknowledged silently.
    emit({ type: 'response.output_item.done', item: { type: 'function_call', name: 'voice_command', call_id: 'call_2', arguments: '{"command":"open_calendar"}' } });
    await c.until(() => c.of('tool_command').length > 0);
    expect(c.of('tool_command')[0].command).toBe('open_calendar');
    await c.until(() => seen.rt.some(e => e.type === 'conversation.item.create' && e.item.call_id === 'call_2'));

    // Barge-in: the user talks over GPT, so the answer stops.
    emit({ type: 'response.output_audio.delta', response_id: 'r2', delta: Buffer.alloc(480, 1).toString('base64') });
    await c.until(() => c.of('speech_begin').length === 2);
    emit({ type: 'input_audio_buffer.speech_started' });
    await c.until(() => c.of('speech_end').length === 2);
    expect(c.of('speech_end')[1]).toMatchObject({ id: 'r2', interrupted: true });

    // Ending hands-free closes the OpenAI session.
    c.send({ type: 'listen_cancel' });
    await c.until(() => c.of('live').some(m => !m.on));
    await new Promise(r => setTimeout(r, 50));
    expect(rt.readyState).not.toBe(WebSocket.OPEN);
    c.ws.close();
  });

  it('strict mode flags GPT answering on its own', async () => {
    const c = client(); await c.open;
    seen.rt.length = 0;
    c.send({ type: 'settings', settings: { engine: 'realtime' } });
    c.send({ type: 'listen', mode: 'conversation' });
    await c.until(() => c.of('live').some(m => m.on) && seen.rt.some(e => e.type === 'session.update'));
    rtSocket!.send(JSON.stringify({ type: 'response.output_audio_transcript.done', response_id: 'r9', transcript: 'You probably have about four deals closing.' }));
    await c.until(() => c.of('mismatch').length > 0);
    expect(c.of('mismatch')[0].source).toBe('');
    c.send({ type: 'listen_cancel' });
    c.ws.close();
  });
});
