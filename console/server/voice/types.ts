// Provider interfaces (voice spec §15). Each STT or TTS provider is swappable behind these, so the
// bridge, the protocol and the browser never change when a provider does.
import type { VoiceMode, Word } from '../../shared/voice';

export interface SpeakOpts { voiceId: string; modelId?: string; rate: number; lang?: string; fast?: boolean }
export interface SpeakHandlers { audio(pcm24k: Buffer): void; words(w: Word[]): void; end(ok: boolean, error?: string): void }

export interface TtsEngine {
  speak(id: string, text: string, o: SpeakOpts, h: SpeakHandlers): Promise<void>;
  cancel(id: string): void;
  close(): void;
}

export interface SttHandlers { started(): void; partial(t: string): void; final(t: string): void; nothing(): void; error(msg: string): void }
export interface SttOpts { lang?: string; prompts?: string[] }
export interface SttStream { push(pcm16k: Buffer): void; finish(): void; cancel(): void }
export type SttFactory = (mode: VoiceMode, o: SttOpts, h: SttHandlers) => SttStream;

/** A batch transcriber: one WAV in, one transcript out (OpenAI, ElevenLabs). */
export type Transcribe = (wav: Buffer, o: SttOpts, signal: AbortSignal) => Promise<string>;
