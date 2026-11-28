# Sales Mama Voice: Design Spec v1

> **Status:** in progress (2026-11-28). V1–V3 are built and tested on branch `voice` (worktree `sales-mama-voice/worktree`). Configurable providers (§15) and voice navigation (§16) were added on request. V4–V7 are still to do. Owner: manager.
> **Applies to:** `console/` (voice UI, the voice bridge and the protocol), `scripts/connect.py` (Inworld key setup), `AGENTS.md` and the skills (spoken answers, Phase V4, which needs plan mode), plus a new ADR-0011.
> **Builds on:**
> - `docs/Frontend_Design_Spec.md` v2 (shell, chat v2, visual system, motion)
> - `docs/UI.md`
> - ADR-0005 (data residency)
> - ADR-0006 (the console renders only)
> - ADR-0007 (approve-then-send)
> - ADR-0009 (scripts emit data, views are A2UI)
>
> **Voice platform:** Inworld AI (`platform.inworld.ai`, docs at `docs.inworld.ai`). It provides speech-to-text (STT), text-to-speech (TTS) and voice design.

---

## 0. Why this spec

Reps spend their day between meetings, in taxis and on the phone. In those moments typing a prompt is the slowest part of Sales Mama. Today the console is keyboard-first, which suits a rep at a desk. The goal is a **Siri-like voice mode**: tap or hold, speak (*"Brief me on Kestrel Physio before my two o'clock"*), and hear a short, grounded answer while the cards still appear on screen.

The hard part is not speech; Inworld provides that. The hard part is keeping voice **inside the harness**. Sales Mama's value comes from its rules:
- skills
- AGENTS.md hard rules
- permissions
- approve-then-send
- grounded facts

A voice assistant with its own LLM brain would bypass all of them. So the central design decision is:

> **Inworld is Sales Mama's ears and mouth, never its brain.** The brain stays the local Claude Code CLI (or `codex exec`), running the same skills and permission settings as a rep typing in a terminal.

| # | Gap today | Phase |
|---|---|---|
| 1 | Answers can only be read, not heard | V1 |
| 2 | Prompts can only be typed | V2 |
| 3 | Back-and-forth needs hands: no turn-taking or barge-in | V3 |
| 4 | Skills write for the eye (tables, paths, cards), not the ear | V4 |
| 5 | The Singapore, Malaysia and India markets need English, Malay, Mandarin, Tamil and Hindi, and local names | V5 |
| 6 | No "Hey Mama" and no pre-meeting spoken briefing | V6 |

**Goal:** speak to Sales Mama like Siri. Each spoken answer is short, grounded and interruptible. It never approves, sends or assigns anything, and it feels like part of the Sales Mama product, not a bolted-on widget.

---

## 1. Principles

The ten console principles stay (UI.md §1 and Frontend spec §1). Six voice principles are added:

11. **Ears and mouth, not brain.** Every spoken request becomes an ordinary console prompt. Skills, AGENTS.md, `.claude/settings.json` and the Codex config apply unchanged. Voice adds no tool, no permission and no model.
12. **The voice never holds the pen.** Speech can *ask* for a draft, a preview or a proposal, but it can never *approve* one. Sending stays a click on Claude Code's `permissions.ask` prompt (ADR-0007), and allocation stays the manager's approval. A spoken "yes, send it" gets this reply: *"Sending needs your click in Claude Code."*
13. **Say less, show more.** The voice speaks the answer's lead (at most about 40 words, Perplexity's "answer first"). Tables, sources and cards stay on screen. The voice never reads a table, a path, a URL or code.
14. **Speech is grounded too.** Spoken numbers are bound to the same data as the cards (ADR-0009): they are filled from `dataRef`, never typed by the model. If the voice and the card ever disagree, that is a bug and an eval failure.
15. **Instant feedback, honest waiting.** An earcon plays within 150 ms and a short spoken acknowledgement follows within about 600 ms. Agent runs then take seconds; the UI shows that honestly with the pulse bar and lanes, and says nothing to fill the silence.
16. **Private by default.** The default is push-to-talk with no always-on microphone. No audio is stored anywhere. Transcripts live only where typed prompts already live: in the browser's chat history.

**Non-negotiables** (unchanged ADRs, restated for voice):
- The console, and so the voice, only sends prompts and renders. It never writes the repo or sends a message, and it never widens permissions (ADR-0006/0007).
- Rep scoping (rule 16): a spoken *"what about Arun's accounts?"* gets the same refusal as a typed one.
- External content is data (rule 15). The voice may speak text that came from `raw/`, but never acts on it. The speakable filter (§6.4) strips anything instruction-shaped.
- No emoji and no gradient washes, and that includes the voice orb (§7).

---

## 2. References: what we take, what we leave

| Product | Take | Leave |
|---|---|---|
| **Siri / Apple Intelligence** | One glowing focal point that shows state (listening, thinking, speaking); a short spoken answer with the detail on screen; tap to interrupt | The full-screen takeover; a rainbow gradient edge glow (it breaks our no-gradient rule) |
| **ChatGPT Advanced Voice** | Barge-in: talk over it and it stops; natural turn-taking | Voice as a separate app mode that hides the chat; free-form chit-chat with no grounding |
| **Google Assistant / Gemini Live** | Live captions while listening; suggestion chips after an answer | Always-on hotword by default |
| **Superhuman / Raycast** | Hold a key to dictate and release to send; speed as a feature | |
| **Car mode (CarPlay)** | Large targets, minimal reading, one thing at a time | |

**Signature voice elements, unique to Sales Mama:**

1. **Mama orb.** A 56 px violet disc in the composer, drawn as solid rings, not a gradient. Its *shape* shows state:
   - idle: still
   - listening: rings breathe with the input level
   - thinking: a lime arc orbits, the same lime as the pulse bar
   - speaking: rings ripple with the output level
2. **Agent voices on the story line.** When the voice speaks, the story line (Frontend spec §2, item 5) lights word by word, using Inworld's word timestamps. You see which agent's result is being spoken in that agent's hue.
3. **Read-back chip.** A spoken prompt first lands as an editable transcript chip, `"brief me on Kestrel Physio"`, with the resolved `@Kestrel Physio` mention. A 1.5 s ring then auto-sends it. Any key or tap pauses the ring so you can edit.
4. **Market-aware voice.** The voice greets you and reads times in your market's zone: *"It's 10:42 in Singapore; the send window is open."* It also pronounces account names from a curated lexicon (Phase V5).
5. **Next-up briefing.** Fifteen minutes before a meeting, the next-up capsule offers *Brief me aloud*: a 30-second spoken brief from `/mama-brief`, made for the walk to the meeting room.

---

## 3. Choosing the Inworld building blocks

Inworld offers three ways to build voice. The facts below come from `docs.inworld.ai` as of 2026-11-28; re-check them before each phase starts.

| Option | What it is | Fit with Sales Mama |
|---|---|---|
| **A. Realtime API** (speech-to-speech, OpenAI Realtime-compatible, WebSocket or WebRTC) | Inworld runs STT, then an LLM of its choice (`provider/model`, default Gemini 2.5 Flash), then TTS in one session, with semantic VAD and server-side interruption | **Rejected as the brain.** The LLM would replace Claude Code or Codex, so skills, AGENTS.md rules and permissions would not apply (this breaks principle 11 and ADR-0006). The browser also needs session tokens, which the docs mark as deprecated. **Update (2026-11-28):** a realtime engine is now offered as *GPT live* (OpenAI Realtime), but only as a relay: GPT must call Sales Mama for anything about work and says only Sales Mama's answer (§15.3) |
| **B. Cascaded STT + TTS** (STT and TTS bidirectional WebSockets) | We stream mic audio to STT and get transcripts with turn detection. We send the transcript to *our* engine, then stream the answer text to TTS and play the audio | **Chosen.** The brain stays the local CLI, and each piece can be tested and replaced |
| **C. LLM + TTS in one request** (`/v1/chat/completions` with voice responses) | Inworld's router LLM answers and speaks | Rejected for the same reason as A |

### 3.1 Inworld services used

| Need | Inworld service | Settings (initial) |
|---|---|---|
| Speech to text, streaming | `wss://api.inworld.ai/stt/v1/transcribe:streamBidirectional` | `modelId: inworld/inworld-stt-1`, `audioEncoding: LINEAR16`, 16 kHz, 16-bit mono. Turn detection is on for conversation mode (`endOfTurnConfidenceThreshold: 0.4`, `maxTurnSilence: 768 ms`). Manual mode for push-to-talk: `vadThreshold: 0`, then `endTurn` on release. Events: `speechStarted`, `speechStopped`, partial and `isFinal` transcripts |
| Text to speech, streaming | `wss://api.inworld.ai/tts/v1/voice:streamBidirectional` | Model `inworld-tts-2` for answers (about 100 ms P90 server time to first byte) and `inworld-tts-2-flash` for acknowledgements (about 20 ms). PCM 24 kHz. `autoMode` with `SENTENCE_BOUNDARY`, because we stream text as the agent writes it. `timestampType: WORD` for captions and the story line. One `contextId` per turn, with `cancelContext` on barge-in, which also stops billing for unspoken text |
| Fixed phrases | `POST /tts/v1/voice` (sync) | About 40 acknowledgement and earcon-paired phrases, pre-synthesised once per voice and cached on disk outside the repo. They cost nothing per use and play with no delay |
| The "Mama" voice | Voice design (`POST /voices/v1/voices:design`) from a text prompt, or a stock voice | **No cloning of a real person's voice** without their written consent (§9). Each rep can pick a voice in their profile (V5) |
| Pronunciation | Custom pronunciation (IPA) and SSML `<break>` | A lexicon for account and people names (V5) |

> **Note:** `tts-1` and `tts-1-max` were discontinued on 2026-06-15, and `tts-1.5` is deprecated. Use the `tts-2` family only.

### 3.2 Authentication and keys

- **The key never reaches the browser.** The console server holds the Inworld key and talks to Inworld server-to-server with `Authorization: Basic <key>`. The browser talks only to the localhost console server, as it does today. One-time browser tokens (`POST /auth/v1/tokens`) are not needed, which keeps the browser simple and the key out of DevTools.
- **Storage:** `~/.config/sales-mama/inworld.json` (mode 600), like the Gmail and WhatsApp tokens (SECURITY.md).
  - Set up with `! python3 scripts/connect.py inworld`. The person types the key, and it never passes through the model.
  - `guard.py` and `lint.py` gain a pattern for Inworld key strings.
  - `INWORLD_API_KEY` in the environment is also accepted for development.
- **One account per team.** It is billed to the manager's Inworld account. Rate limits are per account (On-Demand: 10 concurrent STT streams and 50 TTS sockets), which is enough for one manager and five reps.

---

## 4. Architecture

```
 browser (localhost:4173)                         console server (Node, localhost)                     outside
┌───────────────────────────────┐   /mama  (JSON, unchanged)    ┌──────────────────────────────┐
│ Chat v2 · Composer · Mama orb │◀────────────────────────────▶│ index.ts  ── Run ──spawn──▶ claude -p … (or codex exec --json)
│                               │                               │      │ turn events            │
│ mic ─▶ AudioWorklet (16k PCM)─┼─▶ /mama/voice (binary+JSON) ─▶│ voice/bridge.ts               │
│                               │                               │   ├─ stt.ts ──WSS──────────────┼──▶ Inworld STT
│ speaker ◀─ AudioWorklet ring ◀┼── PCM 24k + word timings ◀────│   ├─ tts.ts ──WSS──────────────┼──▶ Inworld TTS
│ captions · story-line glow    │                               │   ├─ speakable.ts (text → ear) │
└───────────────────────────────┘                               │   └─ phrases.ts (cached acks)  │
                                                                └──────────────────────────────┘
```

**Flow of one spoken turn:**
1. Hold or tap the orb. The browser opens the mic with `echoCancellation`, `noiseSuppression` and `autoGainControl`, resamples to 16 kHz PCM16 in an AudioWorklet, and streams 20 ms frames on `/mama/voice`.
2. `stt.ts` relays the frames to Inworld STT. Partial transcripts flow back to the composer as live captions.
3. At the end of the turn (release in push-to-talk, or Inworld end-of-turn in conversation mode), the final transcript goes through `resolve-mentions`: spoken account names are fuzzy-matched against *your own* accounts (`/api/accounts`, rule 16). The result appears as the read-back chip.
4. After the 1.5 s read-back ring, the transcript becomes an ordinary `{type:'prompt'}` on `/mama`, exactly like typed text. From here the existing engine, stream mapping and cards run unchanged.
5. On `turn_start`, the bridge plays an earcon and a cached acknowledgement chosen by skill ("Checking your book." or "Pulling the brief.").
6. When the turn ends, `speakable.ts` builds the spoken answer (§6.4). `tts.ts` streams it, and audio and word timings flow back to the browser, which plays them and lights the captions.
7. If you start talking while it speaks (barge-in), the browser stops playback within 100 ms, the bridge sends `cancelContext`, and a new listening turn starts.

**Why a separate `/mama/voice` socket:**
- Audio is binary and high-rate. The `/mama` socket keeps its 64 KB JSON contract, its tests and its "one run at a time" rule untouched.
- The voice socket uses the same `sameOrigin` check and is localhost only.

**Engine-agnostic:** the bridge listens to the same `ServerMsg` turn events, so voice works with the Claude Code and Codex engines alike. It is a harness for Claude and Codex, with ears and a mouth.

### 4.1 Files

```
console/server/voice/
  bridge.ts      session per browser socket; state machine; wires STT, engine turns and TTS
  stt.ts         Inworld STT WebSocket client (reconnect, backoff with jitter on 429)
  tts.ts         Inworld TTS WebSocket client (contexts, cancel, timestamps)
  key.ts         reads ~/.config/sales-mama/inworld.json or INWORLD_API_KEY; never logs it
  phrases.ts     acknowledgement catalogue + on-disk cache (~/.cache/sales-mama/voice/)
console/shared/
  voice.ts       VoiceClientMsg / VoiceServerMsg types; pure state machine (tested)
  speakable.ts   markdown/surface → spoken text (pure, tested)
  mentions.ts    spoken name → account id (pure, tested; Jaro-Winkler + phonetic key)
console/src/voice/
  Orb.tsx · Captions.tsx · ReadBack.tsx · VoiceSettings.tsx
  useVoice.ts    mic, worklets, socket, state
  worklets/capture.js · worklets/playback.js
console/src/styles/voice.css
```

There are **no new runtime dependencies in the browser**: AudioWorklet, Web Audio and WebSocket are built in. The server uses the existing `ws`, plus Inworld's endpoints called directly. The `@inworld/tts` Node SDK is optional; raw WebSockets keep control of cancel and timing.

### 4.2 Protocol (`console/shared/voice.ts`)

```ts
export type VoiceMode = 'push' | 'conversation';
export type VoiceState = 'off' | 'idle' | 'listening' | 'hearing' | 'confirming'
                       | 'thinking' | 'speaking' | 'interrupted' | 'error';

export type VoiceClientMsg =                       // JSON frames; audio goes as binary frames (PCM16 16 kHz mono, 20 ms)
  | { type: 'voice_start'; mode: VoiceMode; lang?: string }   // open mic turn
  | { type: 'voice_end' }                                     // push-to-talk released → endTurn
  | { type: 'voice_cancel' }                                  // discard this utterance
  | { type: 'confirm'; text: string; mentions: string[] }     // read-back accepted (possibly edited)
  | { type: 'speak_stop' }                                    // stop talking now (barge-in, Esc)
  | { type: 'speak'; what: 'brief' | 'last'; turnId?: string } // replay or "Brief me aloud"
  | { type: 'settings'; voiceId?: string; rate?: number; lang?: string; speakAnswers?: boolean };

export type VoiceServerMsg =                       // JSON frames; TTS audio goes as binary frames (PCM16 24 kHz mono)
  | { type: 'state'; state: VoiceState; detail?: string }
  | { type: 'partial'; text: string }
  | { type: 'final'; text: string; mentions: { said: string; id: string; conf: number }[]; lang?: string }
  | { type: 'speech_begin'; turnId: string; text: string; agent?: string }
  | { type: 'words'; words: { w: string; start: number; end: number }[] }   // timestamps for captions
  | { type: 'speech_end'; turnId: string; interrupted: boolean }
  | { type: 'voice_error'; message: string; fix?: string };    // e.g. "No Inworld key: run ! python3 scripts/connect.py inworld"
```

### 4.3 Voice state machine

```
 off ──enable──▶ idle ──hold/tap──▶ listening ──speech──▶ hearing ──end of turn──▶ confirming
                  ▲                     │ cancel/silence 8 s                         │ 1.5 s ring or ⏎
                  │                     ▼                                            ▼
                  ├──────────────── idle ◀──────── speaking ◀──── turn_end ──── thinking (engine run)
                  │                                   │ user speaks / Esc / tap
                  └──────────── listening ◀── interrupted (cancelContext, stop playback ≤ 100 ms)
```

- `confirming` is skipped for a follow-up chip chosen by voice ("yes, the second one"), because the chip text is already a known prompt.
- While the engine is busy (`busy`), a new spoken prompt is queued, just as Composer v2 queues typed ones.

---

## 5. Interaction design

### 5.1 Modes

| Mode | Gesture | Mic | When |
|---|---|---|---|
| **Push-to-talk** (default) | Hold the orb, or hold `⌥Space`; release to finish | Open only while held | At a desk, in an open office |
| **Tap-to-talk** | Tap the orb; Inworld end-of-turn finishes it | Open for one utterance, closes after 8 s of silence | Quick one-handed asks on the phone |
| **Conversation** | Double-tap the orb or press `⌥⇧Space`; tap again to end | Open between turns; barge-in on | Hands-busy moments, the walk to a meeting. Opt-in per session, with a visible lime "mic on" chip in the header |

There is no always-on microphone. The "Hey Mama" wake word is Phase V6, opt-in and detected on the device.

### 5.2 Composer with voice

```
┌──────────────────────────────────────────────────────────────────────────┐
│ "brief me on kestrel physio before my two o'clock"   ◔ sending…  Edit   │  read-back chip (1.5 s ring)
│ @Kestrel Physio ×   SG window open                                       │  resolved mentions
├──────────────────────────────────────────────────────────────────────────┤
│ /  @  ⌘K   /mama-brief  /mama-day  …                    (◉ orb)  [ ➜ ]  │  orb sits left of send
└──────────────────────────────────────────────────────────────────────────┘
```

- **Live captions:** partial transcripts stream into the composer in muted ink. The final text turns full ink.
- **Low-confidence mentions:** a match with confidence below 0.9 shows as a dashed chip with alternatives (`Kestrel Physio · Kestrel Pharma`). The ring pauses until you pick one; nothing is guessed (as with rule 10).
- **Spoken commands** map to the existing keyboard and skill vocabulary, with no new verbs:
  - "new chat"
  - "stop" (the same as Esc)
  - "read that again"
  - "open the calendar"
  - "the second one" (follow-up chip 2)
- **"Send it" and "approve":** the orb answers with the fixed reply (principle 12) and highlights the *Copy command* or approval banner. It never sends a click for you.

### 5.3 What the voice says

| Moment | Spoken (example) | Source |
|---|---|---|
| Run starts | "Checking your book." | Cached phrase, picked by skill |
| Long run (> 12 s) | nothing (the pulse bar shows progress) | Optional setting: one line every 15 s, e.g. "Researcher is on Kestrel." |
| Answer | "You have three meetings today. Next is Kestrel Physio at two, in twenty-five minutes. Two follow-ups are due." | `mama-voice` block, with numbers bound to `dataRef` (V4) |
| Needs approval | "Four drafts are ready. Sending needs your click in Claude Code." | Fixed template + count from the turn |
| Error | "I couldn't reach Claude Code. Check that it's signed in." | `turn_end.error.message` → speakable |
| Follow-ups | "Want me to draft the follow-up, or compare the top three?" | The turn's follow-up chips (at most 2 spoken) |

### 5.4 Keyboard and touch

| Keys / gesture | Action |
|---|---|
| Hold `⌥Space` | Push-to-talk |
| `⌥⇧Space` | Toggle conversation mode |
| `Esc` | Stop speaking, cancel listening or stop the run, in that order |
| `⌘.` | Replay the last spoken answer |
| `⏎` in read-back | Send now |
| any other key in read-back | Pause the ring and edit |
| Touch | 56 px orb (above the 44 px minimum); long-press = push-to-talk; on mobile the orb sits in the thumb zone, centred above the tab bar |

### 5.5 Accessibility

- Every spoken answer is also on screen; voice is never the only channel.
- Captions are on by default and use the same type scale.
- Screen readers: the orb has `aria-pressed` and a live region that announces the state ("Listening", "Sales Mama is speaking"). When a screen reader is detected, `speakAnswers` defaults to off to avoid two voices at once, and the user can turn it on.
- Speaking rate is 0.8–1.3× (Inworld's range is 0.5–1.5), with the setting saved in the browser.

---

## 6. Spoken answers (the "ear" layer)

### 6.1 Phase V1–V3: speak the lead line

AGENTS.md already says that, in console mode, a skill ends with *"a one-line plain-text summary"* before its surfaces. V1–V3 speak that line, after the speakable filter, and nothing else. This needs no change to skills.

### 6.2 Phase V4: `MAMA_VOICE=on` and the `mama-voice` block (plan mode)

When voice is on for a turn, the console appends `MAMA_VOICE=on` alongside `MAMA_CARDS=on` (one more `--append-system-prompt` value; still not a permission flag, and the forbidden-flags test is unchanged). AGENTS.md gains a section:

````md
## Voice mode
When the session says `MAMA_VOICE=on`, after the summary and surfaces add one ```mama-voice block:
- at most 40 words (a brief: 80), spoken English (or the rep's `voice.lang`), no markdown, paths, URLs or code
- numbers only as {{bindings}} into a surface's dataRef (ADR-0009), e.g. "{{today.meetings}} meetings today"
- times as words in the account market's zone; currency as "S$12,400" (the TTS reads it)
- never say a draft was sent or approved; say what needs the rep's click
````

The bridge fills `{{bindings}}` from the same JSON the cards render. If a binding is missing, that sentence is dropped, not guessed.

### 6.3 Example

````md
```mama-voice
{"text": "You have {{day.meetings}} meetings today. Next is {{next.account}} at {{next.time_words}}. {{day.followups_due}} follow-ups are due.",
 "dataRef": "wiki/books/praveen.json", "agent": "mama"}
```
````

### 6.4 Speakable filter (`shared/speakable.ts`, pure and tested)

- Strip markdown, code spans, fenced blocks, file paths (`wiki/…`, `scripts/…`), URLs and email addresses. A link is spoken as its text only.
- **Untrusted text:** drop any sentence that is instruction-shaped (imperatives aimed at the assistant, such as "ignore previous", "forward this" or "send to"). A dropped sentence is shown as a one-line warning on screen, as rule 15 requires.
- Normalise:
  - `SG`/`MY`/`IN` become "Singapore", "Malaysia" and "India" the first time they appear
  - `14:00+08:00` becomes "two pm"
  - `A/B/C` tier becomes "tier A"
  - `fu1` becomes "first follow-up"
- Cap the output at 60 words, or 120 for briefs. Cut at a sentence boundary, never mid-sentence.
- Emoji are removed: they cost two billable characters each and the voice shouldn't say them.

---

## 7. Visual system for voice

The voice uses the Frontend spec §7 tokens only, with no new colours.

| Element | Light | Dark | Motion |
|---|---|---|---|
| Orb, idle | Mama `#6D28D9` disc, 2 px `#EFE8FF` ring | `#A78BFA` disc, `#2A2142` ring | none |
| Orb, listening | Disc + 3 rings that scale with input RMS (transform only) | same | `--t-fast` per level update, capped at 30 Hz |
| Orb, thinking | Disc + 2 px lime `#C8F031` arc orbiting | same | 1.6 s linear loop, matching the activity shimmer |
| Orb, speaking | Rings ripple outward with output RMS, in the speaking agent's hue | same | `--t-base` |
| Orb, error | Risk `#B91C1C` ring with an SVG mic-off glyph | `#F87171` | one 120 ms shake, or none under reduced motion |
| Captions | 15 body in muted ink; the spoken word in ink with a lime underline | same tokens | the underline moves via `transform` |
| "Mic on" chip (conversation) | Lime on ink, mono "MIC ON" | same | 2 s pulse, like the now dot |
| Read-back ring | 2 px Mama ring filling over 1.5 s | same | conic fill via `stroke-dashoffset` |

- There is no gradient: the "glow" is made of solid concentric rings with opacity steps (0.24, 0.12, 0.06).
- **Reduced motion:** the rings don't scale. State is shown by a static ring count (1 to 3) plus the text label. There is no orbit; the thinking state uses a static lime arc.
- State is always shown by **shape and label**, never by colour alone.

---

## 8. Latency budget

| Step | Target (P90, local Wi-Fi, SG) | How |
|---|---|---|
| Press → earcon | ≤ 50 ms | Local Web Audio buffer |
| End of speech → final transcript | ≤ 700 ms (push-to-talk), ≤ 900 ms (conversation) | Manual `endTurn` on release; tuned `maxTurnSilence` |
| Final transcript → read-back shown | ≤ 50 ms | Local mention matching |
| Prompt sent → spoken acknowledgement | ≤ 300 ms | Cached phrase, no network |
| Turn end → first answer audio | ≤ 400 ms | `tts-2` about 100 ms TTFB + network; the bridge starts TTS as soon as the voice block arrives, not at `turn_end` |
| Barge-in → silence | ≤ 100 ms | Browser stops playback locally first, then `cancelContext` |
| Agent run itself | 3–40 s (unchanged) | Not a voice problem; shown honestly (principle 15) |

The end-to-end Inworld numbers above are targets, not documented guarantees. Inworld documents TTS time to first byte only, so V0 measures the real values.

---

## 9. Privacy, compliance and safety

| Topic | Rule |
|---|---|
| Audio | Streamed to Inworld for transcription only, never stored by Sales Mama (no `raw/`, no logs, no cache). Check Inworld's retention and DPA terms, and turn on any zero-retention option, before V2 |
| Transcripts | Stored like typed prompts: only in browser chat history (Frontend spec §5.5). Never written to the repo |
| Data residency (ADR-0005) | Inworld becomes a third processor next to the model provider and GitHub. Spoken prompts may contain business contact names (largely exempt in SG) and, in conversation mode, bystanders' voices. Add Inworld to the ADR-0005 checklist for SG PDPA, MY PDPA 2024 (cross-border transfers) and India DPDP, and get the DPO's sign-off before V2 ships to reps |
| Bystanders | Push-to-talk is the default. Conversation mode shows the "MIC ON" chip and auto-stops after 2 minutes idle. Never record meetings or calls: the voice is for the rep's own requests, and AGENTS.md rule 14 ("never automate calls") applies |
| Voice cloning | No cloning of any real person (rep, manager, customer) without their written consent stored outside the repo. The default "Mama" voice is a designed voice, not a clone. Never use a customer's voice. Spoken output is never sent to customers; it is not an outreach channel |
| Approvals | Voice cannot approve (principle 12). `eval.py` gains a check: no `sent` touch may have a turn whose approval came from a spoken utterance (target 0). The approval is always the `permissions.ask` click |
| Prompt injection by voice | A spoken prompt is treated exactly like a typed prompt from the signed-in user. Audio from a speaker in the room (for example, a video that says "send all drafts") still can't approve anything |
| Key handling | `connect.py inworld`, mode 600, guard and lint patterns, rotation in GUIDE.md §9 when someone leaves |
| Cost guard | A per-user daily character cap in `voice.settings` (default 20,000 characters, about 20 minutes of speech). Past it, the voice says "Voice limit reached for today" once and switches to text |

**SECURITY.md additions (OWASP LLM):**
- LLM01: spoken injection is treated as text.
- LLM02: no audio is stored.
- LLM06: voice adds no agency.
- LLM10: the cost guard and the STT concurrency limit.

---

## 10. Cost estimate

These are list prices from `inworld.ai/pricing`, read on 2026-11-28; confirm them before budgeting.

| Item | Assumption | Monthly |
|---|---|---|
| TTS (`tts-2`) | 6 users × 50 spoken answers a day × about 300 characters × 22 days ≈ 2.0 M characters | ≈ US$50 On-Demand ($25 per M), ≈ US$30 Developer ($15 per M) |
| TTS (flash, acknowledgements) | Cached, so close to 0 characters | ≈ US$0 |
| STT | 6 users × 30 minutes a day × 22 days ≈ 66 hours | ≈ US$10 ($0.15 per hour) |
| **Total** | | **≈ US$40–60 a month for the team.** The free On-Demand tier (about 70 TTS minutes and 400 STT minutes) covers V0–V1 |

`cancelContext` on barge-in limits billing to the text actually synthesised.

---

## 11. Implementation phases

### Status (2026-11-28)

| Phase | Status | What exists |
|---|---|---|
| V0 | **Partly done** | Inworld key in `~/.config/sales-mama/inworld.json` (mode 600). Latency measured (§17). `npm run voice:check` checks every provider with a key against the real APIs. Still to do: ADR-0011, the DPO sign-off for ADR-0005, guard and lint key patterns, and the 60-utterance consented test set |
| V1 | **Built** | Speaker toggle, lead line spoken through the speakable filter, word-timed captions, cached acknowledgements, voice picker, daily cost guard |
| V2 | **Built** | Hold-to-talk (orb or `⌥Space`), tap-to-talk, live captions, spoken account names matched only to your own accounts, read-back chip with a 1.5 s ring, and a guard so that a match below 0.9 never auto-sends |
| V3 | **Built** | Hands-free mode with barge-in, spoken commands and follow-up picks, the fixed "send it" reply, the MIC ON chip and the 2-minute idle stop. Also *GPT live* (§15.3) |
| V4–V7 | To do | V4 needs plan mode (AGENTS.md and skills). V5 has a language setting and a voice picker, but no pronunciation lexicon yet. The browser end-to-end scripts are not yet in CI (V7) |

**Tests:** 240 Vitest tests, all passing. They cover the speakable filter, commands, mentions and the grounding guard, plus the bridge against mock Inworld, OpenAI and ElevenLabs servers, including a full GPT live turn. Real-browser runs (Chrome with a fake microphone playing Inworld-rendered speech) passed for:
- push-to-talk, then read-back, then auto-send, then the acknowledgement, then the spoken answer
- four spoken navigation commands

Each phase can ship alone, ends with green tests, and leaves the console usable with voice off. Voice is **off by default** until the user turns it on in Settings.

| Phase | Scope | Key files | Done when | Size |
|---|---|---|---|---|
| **V0 · Decisions & spike** | ADR-0011 (Inworld as ears and mouth only, option B, no Realtime brain). Inworld account and DPA review; ADR-0005 checklist entry. `connect.py inworld` + guard/lint key patterns (plan mode: `scripts/`). Spike: a 20-line Node script that streams a WAV to STT and speaks a sentence via TTS, measuring latency from SG. Record a **consented** test set of 60 utterances from the team (Singapore, Malaysian and Indian English accents; account names from `examples/`) | `docs/adr/0011-voice.md`, `scripts/connect.py`, `scripts/guard.py`, `scripts/lint.py`, `evals/voice/` | ADR accepted by the manager. Key stored with mode 600, and lint blocks a planted key. Spike numbers recorded in the ADR. WER on the test set measured | S |
| **V1 · Mama speaks** (TTS only) | Speaker toggle in the header. At `turn_end`, speak the lead line through the speakable filter. Captions with word timestamps. Stop with Esc or by tapping the orb. Cached acknowledgement phrases. Voice picker (stock or designed voices). Cost guard | `server/voice/{bridge,tts,key,phrases}.ts`, `shared/speakable.ts`, `src/voice/{Orb,Captions,VoiceSettings}.tsx`, `worklets/playback.js` | Vitest: speakable strips paths, URLs, code and instruction-shaped sentences (20 cases). Replay `?replay=mama-day&voice=1` speaks each lead line. Esc stops audio within 100 ms. With no key, a clear `voice_error` with the fix. The forbidden-flags test still passes | M |
| **V2 · Push-to-talk** | Mic permission flow. Capture worklet (16 kHz PCM16). STT in manual mode. Live captions in the composer. Spoken mention resolution (own accounts only). Read-back chip with a 1.5 s auto-send ring. Spoken commands (new chat, stop, open calendar). `⌥Space` hold. **Needs the ADR-0005 DPO sign-off** | `server/voice/stt.ts`, `shared/{voice,mentions}.ts`, `src/voice/{ReadBack,useVoice}.ts`, `worklets/capture.js` | Playwright with Chrome's fake mic (`--use-file-for-fake-audio-capture`) plays recorded utterances and sees the right prompt sent. Account-name resolution ≥ 95% on the test set, with 0 matches to another rep's accounts. A mention below 0.9 confidence never auto-sends. No audio bytes on disk (a test checks the cache and log directories) | M |
| **V3 · Conversation mode** | Inworld turn detection. Barge-in (local stop + `cancelContext`). Follow-up chips spoken and chosen by voice ("the second one"). The "approve or send" fixed reply. "MIC ON" chip with a 2-minute idle auto-stop. Queueing while busy | `server/voice/bridge.ts` (state machine), `src/voice/*`, `src/app/Header.tsx` | A scripted 5-turn hands-free session passes in Playwright. Barge-in in under 100 ms. Saying "send it" never triggers a send (eval). A missed end-of-turn is under 5% on the test set | M |
| **V4 · Spoken answers by design** (plan mode) | `MAMA_VOICE=on`; the `mama-voice` block with `{{bindings}}` filled from `dataRef`; AGENTS.md "Voice mode" section; update the 8 most-used skills (mama-day, mama-book, mama-brief, mama-replies, mama-schedule, mama-manager, company-check, company-insights); 80-word spoken brief; selftest and eval cases | `AGENTS.md`, `.agents/skills/*` (→ `sync_skills.py`), `server/engine.ts` (one more append value), `shared/speakable.ts` (bindings) | A failing selftest is written first, then turns green. eval: spoken numbers equal card numbers (0 mismatches). 0 fabricated names in voice blocks. No paths or URLs in any voice block. Codex parity: the same blocks come from `codex exec` | L |
| **V5 · Markets & languages** | `voice:` in `reps/<id>.md` (voiceId, lang, rate). Malay, Mandarin, Tamil and Hindi TTS voices. STT language auto-detect with a per-rep default. `knowledge/pronunciation.yaml` (manager-owned) with IPA for account and people names. Times and currency per `markets.yaml`. Non-English answers flagged "auto-translated" on screen | `templates/rep.md`, `knowledge/pronunciation.yaml`, `server/voice/tts.ts`, `scripts/lint.py` (schema) | Each market's test set passes its WER target (set in V0). The lexicon fixes the 20 hardest names. A rep's voice and language persist. Lint validates `pronunciation.yaml` | M |
| **V6 · Wake word & on-the-go** (optional) | Opt-in "Hey Mama" wake word detected on the device (a WASM keyword model in an AudioWorklet; no audio leaves the device until it triggers). *Brief me aloud* from the next-up capsule and the 15-minute reminder. Car layout: one big orb, captions, no cards. **Phone access beyond localhost needs its own ADR** (the console is localhost-only today) | `src/voice/wake/*`, `src/calendar/NextUp.tsx`, `src/voice/CarMode.tsx` | False wakes below 1 per hour in office noise. Triggers ≥ 95% on the test set. No network traffic before a wake, checked in DevTools and an e2e test | M |
| **V7 · Hardening** | Playwright voice e2e in CI (fake mic + mocked Inworld), latency dashboard from bridge timings, a11y audit (screen reader + voice), visual snapshots of all orb states (light/dark, reduced motion), docs (UI.md voice section, README, GUIDE.md §9 key rotation), a demo replay with voice for the films | `console/e2e/voice.*`, `.github/workflows/ci.yml`, `docs/*` | CI green with voice e2e. P90 latencies meet §8. Lighthouse a11y ≥ 95 with voice on. Docs updated | M |

**Suggested order:** V0 → V1 → V2 → V3 → V4 → V5 → V7, with V6 when the team wants it.
- V1 can start before the DPO sign-off: it sends only Sales Mama's own answer text to Inworld, not the user's voice.
- V4 can overlap V3 once the `mama-voice` block shape (§6.2) is frozen.

### Phase prompts (paste into Claude Code, one per phase)

- **V0:** "Read `Sales-Mama-Voice-design-spec.md` §3 and §9. In plan mode, write ADR-0011 and extend `connect.py`, `guard.py` and `lint.py` for an Inworld key. Write failing selftests first."
- **V1:** "Implement Phase V1 of the voice spec. Start with `shared/speakable.ts` and its Vitest cases, then `server/voice/tts.ts`, then the Orb and Captions. Voice off by default. Show me screenshots of every orb state."
- **V2–V7:** the same pattern. Name the phase, list its "Done when" checks as tests to write first, and ask for screenshots before review.

---

## 12. Testing and evals

- **Vitest (pure):**
  - the speakable filter
  - mention resolution: phonetic matching and other reps' accounts excluded
  - the voice state machine: every transition, including barge-in in each state
  - binding fill: a missing binding drops the sentence
- **Mock Inworld:** a local WebSocket server that replays recorded STT events and streams fixed PCM, so CI never calls Inworld or needs a key.
- **Playwright:** Chrome's fake mic with WAV fixtures; checks the prompt text sent on `/mama`, the read-back, barge-in timing, and the orb states in light, dark and reduced motion.
- **Evals (`evals/voice/`):**
  - WER per accent group
  - account-name accuracy
  - end-of-turn misses
  - spoken-equals-card numbers (0 mismatches)
  - fabricated names in voice blocks (0)
  - voice-triggered approvals (0)
  - average spoken words per answer (≤ 40)
- **Manual:** a weekly 10-minute "walk test", where a rep uses conversation mode while walking with earbuds, and the notes go to `docs/LEARNINGS.md`.

---

## 13. Decisions for the manager

1. **Brain.** *Recommended:* the local Claude Code or Codex engine, always. Speech comes from Inworld, OpenAI or ElevenLabs (cascade, §15). *GPT live* (OpenAI Realtime) is allowed only as a strict relay (§15.3): GPT talks, Sales Mama answers.
2. **Default mode.** *Recommended:* push-to-talk, with conversation mode opt-in per session and no always-on mic.
3. **Auto-send after read-back.** *Recommended:* yes, a 1.5 s ring, paused by any key or low-confidence mention. The alternative is always pressing ⏎, which is safer and slower.
4. **The "Mama" voice.** *Decided 2026-11-28:* male by default (Inworld Junhao). Each rep may pick a stock voice, or clone their own voice with written consent recorded outside the repo (the owner's clone exists, §15.4). Never anyone else's voice.
5. **Billing.** *Recommended:* one team Inworld account on the manager, starting On-Demand (free tier) and moving to Creator once V2 is live.
6. **Languages in V5.** *Recommended:* English first; then Malay and Mandarin for MY and SG; then Hindi and Tamil for IN. Non-English answers flagged "auto-translated".
7. **Mobile (V6).** Decide whether the console may be reached beyond localhost, for example over a private tailnet. This needs its own ADR. *Recommended:* defer it; use the laptop with earbuds first.

---

## 14. Risks

| Risk | Mitigation |
|---|---|
| Local accents and names (Singlish, Manglish, Indian English, Chinese, Malay and Tamil names) are misheard | Consented test set in V0; WER targets per group; pronunciation and mention lexicon; read-back chip before sending; confidence below 0.9 never auto-sends |
| Agent runs are slow (seconds), so it doesn't feel like Siri | Instant earcon and acknowledgement; the pulse bar and lanes stay visible; answer audio starts as soon as the voice block streams; avoid filler chatter (principle 15) |
| The voice says something the cards don't (fabrication) | Bound numbers only (V4); speakable filter; eval with 0 mismatches; V1–V3 speak only the skill's own lead line |
| Someone tries "approve" or "send" by voice, or a nearby speaker does | Principle 12; eval check; approval stays a `permissions.ask` click |
| Echo: the assistant hears itself in conversation mode | Browser `echoCancellation`; a short barge-in gate (ignore speech in the first 250 ms of its own audio); recommend earbuds in conversation mode |
| Inworld API changes (tts-1 was discontinued mid-2026) | All Inworld calls sit behind `stt.ts` and `tts.ts`; mock server in CI; model IDs in settings, not code; re-check docs at each phase start |
| Vendor lock-in | Option B keeps STT and TTS swappable (for example ElevenLabs or Deepgram) behind the same `voice.ts` protocol; nothing about the brain is Inworld-specific |
| Privacy: voices and bystanders | Push-to-talk default; no audio stored; MIC ON chip and auto-stop; DPO sign-off before V2 |
| Cost overrun | Short answers (≤ 40 words), cached acknowledgements, `cancelContext` on barge-in, per-user daily cap |
| Rate limits (429 with no Retry-After) | Backoff with jitter in `stt.ts` and `tts.ts`; one STT stream per user; the plan's concurrency covers 6 users |

---

## 15. Configurable providers (added 2026-11-28)

Each part of the voice can come from a different provider, chosen per user in the voice settings panel (header, sliders icon). Defaults for a machine come from `~/.config/sales-mama/voice.json`, kept outside the repo so a personal voice id is never committed. Environment variables can override them: `MAMA_VOICE_STT`, `MAMA_VOICE_TTS` and `MAMA_VOICE_ENGINE`.

| | Inworld | OpenAI | ElevenLabs |
|---|---|---|---|
| **Speech to text** | Streaming WebSocket `inworld-stt-1`, with partial transcripts, turn detection and account names as custom vocabulary | Batch `gpt-4o-mini-transcribe`, with account names in `prompt` | Batch Scribe `scribe_v1` |
| **Text to speech** | Streaming WebSocket `inworld-tts-2`, with word timestamps; `tts-2-flash` for acknowledgements | `gpt-4o-mini-tts`, streaming PCM, no timestamps | Streaming `eleven_flash_v2_5`, with character timestamps turned into words |
| **Hands-free engine** | Cascade (this spec) | **GPT live:** OpenAI Realtime `gpt-realtime` (§15.3) | Cascade |
| **Key file** | `~/.config/sales-mama/inworld.json` | `openai.json`, or `openai.env` with `OPENAI_API_KEY=` | `elevenlabs.json` |

### 15.1 One interface

All providers sit behind two interfaces in `server/voice/types.ts`:
- `TtsEngine`: `speak`, `cancel` and `close`
- `SttStream`: `push`, `finish` and `cancel`

So the protocol and the browser never change when a provider does.

### 15.2 Batch transcribers

OpenAI and ElevenLabs transcribe a whole clip, with no turn detection of their own. `BatchStt` gives them all three modes:
- An energy endpointer runs on 20 ms frames with an adaptive noise floor, 0.7–0.8 s of quiet and 300 ms of pre-roll.
- *Speech started* events still drive barge-in.
- There are no partial transcripts.

### 15.3 GPT live: GPT is the voice, Sales Mama is the brain

Hands-free with the *GPT live* engine opens an OpenAI Realtime session. It uses semantic VAD, server-side interruption, 24 kHz PCM both ways (the mic is resampled from 16 kHz) and the male voice `cedar`. It has exactly two tools:
- `ask_sales_mama(request)`: anything about the user's work. The browser shows the request in the read-back, sends it on `/mama` like typed text, and when the turn ends, hands the lead line back as the tool result. GPT is then told to say it word for word, with `tool_choice: none`.
- `voice_command(command)`: the navigation vocabulary of §16.

Safeguards:
- **Strict mode (default):** `tool_choice: required`. GPT cannot chat or answer from its own knowledge; every user turn is a tool call. With strict off, GPT may greet and clarify, but work questions still go to the tool.
- **Grounding guard:** every number GPT says is checked against Sales Mama's answer, with spelled-out numbers normalised. A mismatch shows *"GPT said a number that is not in Sales Mama's answer. Trust the card on screen."* In strict mode, GPT speaking a number without a tool result is also flagged.
- **Approvals:** a spoken or relayed "send it" gets the fixed reply. GPT has no tool that sends, approves or assigns.
- **Cost:** `MAMA_VOICE_REALTIME_MINUTES` per day, default 30.
- **Privacy:** in GPT live, the user's audio and Sales Mama's spoken answers go to OpenAI. Add OpenAI to the ADR-0005 processor checklist before the team uses it.

### 15.4 Voices

- **Male by default.** Inworld `Junhao` is Singaporean English, measured at a median F0 of 109 Hz. Other measured male voices are listed first in the picker:
  - Singaporean: Zherong, Boonleng
  - Indian: Nikhil, Vikram, Aditya
  - American: Dennis

  OpenAI uses `onyx` (and `cedar` for GPT live). ElevenLabs uses `George`.
- **The owner's own voice.** An Inworld instant clone, "Praveen" (`<workspace>__praveen`), was made at the owner's request on 2026-11-28 from a 26 s clip of their own podcast. Its median F0 is 124 Hz, against 131 Hz in the source. It is the default on the owner's machine through `voice.json`. Consent is recorded in `~/.config/sales-mama/voice-consent.txt`. It is used only for the owner's own assistant, never for customers or other reps.

## 16. Navigating the chat by voice (added 2026-11-28)

Hold `⌥Space` (or the orb), or go hands-free, and speak. A phrase that matches a command runs at once, with no read-back. Anything else is a question for Sales Mama. Each command does exactly what a click or a key already does (`src/voice/navigate.ts`); nothing here writes or sends.

| Say | Does |
|---|---|
| "Previous answer", "next answer", "first answer", "latest answer" | Moves the focus ring through the chat, scrolls to it and reads it: "Answer 2 of 5. …" |
| "Read it", "read that again" | Reads the answer in focus, or repeats the last spoken answer |
| "Open source two", "show the first source" | Opens that numbered source of the answer in focus |
| "Open in canvas", "close" | Opens the answer's view wide, or closes the drawer, canvas or panel |
| "Scroll up", "scroll down", "go to the top", "go to the latest" | Moves the chat |
| "Open the calendar", "my schedule", "my accounts", "reports", "today" | Goes to that view |
| "Next week", "previous month", "go to today", "week view" | Drives the calendar's own keys (← → t d w m) |
| "Open my last chat", "new chat", "search" | Switches conversations or opens ⌘K |
| "The second one", "number for" | Runs that follow-up suggestion |
| "Stop", "mute", "read answers aloud" | Stops speaking, or turns spoken answers off or on |
| "What can I say?" | Speaks a short list and opens the shortcut sheet, which now has a *Say it* section |

The grammar matches the whole utterance, so "brief me on the first meeting", "close the deal with Bluefin" and "what's on next week" stay questions for Sales Mama. There are tests for each. Spoken-number homophones are accepted: "source **too**" was real STT output. GPT live has the same vocabulary through `voice_command`.

## 17. Measured (2026-11-28, Singapore, home Wi-Fi)

| What | Result |
|---|---|
| Inworld TTS over the persistent WebSocket (your cloned voice) | First audio in 688 ms |
| Inworld STT, push-to-talk release to final transcript | About 300 ms (295 ms with `closeStream`, 313 ms with `endTurn`) |
| Browser: orb released → read-back shown → prompt sent | 0.3 s → 1.9 s (including the 1.5 s ring) |
| Inworld round trip of "Brief me on Kestrel Physio before my two o'clock meeting." | Word for word |
| OpenAI TTS `onyx` | First audio in 1.8 s |
| OpenAI STT | 1.4 s, correct |
| GPT live session setup | 2.0 s |
| GPT live relay | GPT called `ask_sales_mama("How many meetings do I have today?")` instead of answering |
| ElevenLabs | Not checked: no key yet. Tested against a mock only |

## Appendix A: Inworld facts used (verify before each phase)

These facts were read from `docs.inworld.ai` on 2026-11-28. Items marked **(unverified)** were not confirmed in the docs.

- **Base URL:** `https://api.inworld.ai`. **Auth:** `Authorization: Basic <key>` on the server. Browser one-time tokens come from `POST /auth/v1/tokens` (single use; TTL up to 1 h; not accepted by Realtime).
- **STT:**
  - **Streaming:** `wss://…/stt/v1/transcribe:streamBidirectional`, which accepts LINEAR16 only (best at 16 kHz mono).
  - **Sync:** `POST /stt/v1/transcribe`.
  - **Model:** `inworld/inworld-stt-1`. About 30 languages, with auto-detect **(list unverified)**.
  - **Turn detection:** `endOfTurnConfidenceThreshold` 0.4 and `maxTurnSilence` 768 ms. Manual mode uses `vadThreshold: 0` with `endTurn`.
- **TTS:**
  - **Streaming:** `wss://…/tts/v1/voice:streamBidirectional`, with contexts (`create`, `sendText`, `flushContext`, `closeContext`, `cancelContext`). At most 2,000 characters per `sendText`.
  - **REST:** `POST /tts/v1/voice` and `:stream`.
  - **Models:** `inworld-tts-2` (about 100 ms P90 time to first byte) and `inworld-tts-2-flash` (about 20 ms).
  - **Formats:** PCM, WAV, MP3, Opus, 8–48 kHz.
  - **Timestamps:** `WORD` or `CHARACTER`, with visemes.
  - **Controls:** speaking rate 0.5–1.5, SSML `<break>`, IPA pronunciation.
  - The name of the audio chunk field in the WebSocket messages is **(unverified)**.
- **Voices:**
  - list: `GET /tts/v1/voices`
  - design: `POST /voices/v1/voices:design`
  - instant clone: `POST /voices/v1/voices:clone`, from 3–30 s of audio
- **Realtime (not used for the brain):** `wss://…/api/v1/realtime/session` or WebRTC `/v1/realtime/calls`. OpenAI Realtime-compatible events, `semantic_vad` / `server_vad`, and `response.speak` to say exact text.
- **Limits (On-Demand):** 10 concurrent STT streams, 50 TTS WebSockets, 5 concurrent TTS generations. An HTTP 429 carries no Retry-After.
- **Pricing:** `tts-2` costs $25 per M characters On-Demand ($15 Developer); flash $15 per M; STT $0.15 per hour. Emoji count as 2 characters.
