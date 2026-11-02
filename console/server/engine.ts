// Drives the local Claude Code CLI headless (docs/UI.md §3, ADR-0006).
// It only sends prompts and relays output. It never adds permission flags: the run uses
// the project's .claude/settings.json exactly as a rep typing in Claude Code would.
import { spawn, type ChildProcess } from 'node:child_process';
import type { StreamEvent } from '../shared/stream';

const SESSION_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Flags the console must never pass (tested). */
export const FORBIDDEN_FLAGS = [
  '--dangerously-skip-permissions', '--allow-dangerously-skip-permissions', '--permission-mode',
  '--allowedTools', '--allowed-tools', '--disallowedTools', '--add-dir', '--settings',
  '--mcp-config', '--permission-prompt-tool',
];

export function buildArgs(prompt: string, sessionId?: string): string[] {
  const args = [
    '-p',
    '--output-format', 'stream-json',
    '--verbose',
    '--include-partial-messages',
    '--append-system-prompt', 'MAMA_CARDS=on',
  ];
  if (sessionId && SESSION_ID.test(sessionId)) args.push('--resume', sessionId);
  // "--" ends option parsing, so a prompt starting with "-" can never become a flag.
  args.push('--', prompt);
  return args;
}

export function claudeBin(): string {
  return process.env.MAMA_CLAUDE_BIN || (process.platform === 'win32' ? 'claude.exe' : 'claude');
}

export interface RunHandlers {
  onEvent(e: StreamEvent): void;
  onEnd(code: number | null, stderr: string, error?: { message: string; fix?: string }): void;
}

export class Run {
  private child: ChildProcess;
  private stderr = '';
  private ended = false;

  constructor(cwd: string, prompt: string, sessionId: string | undefined, h: RunHandlers) {
    this.child = spawn(claudeBin(), buildArgs(prompt, sessionId), {
      cwd,
      env: process.env,
      stdio: ['ignore', 'pipe', 'pipe'], // no stdin: avoids the CLI's 3 s wait for piped input
      windowsHide: true,
    });
    let buf = '';
    this.child.stdout!.setEncoding('utf8');
    this.child.stdout!.on('data', (chunk: string) => {
      buf += chunk;
      let nl: number;
      while ((nl = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (!line.startsWith('{')) continue;
        try { h.onEvent(JSON.parse(line)); } catch { /* ignore a malformed line */ }
      }
    });
    this.child.stderr!.setEncoding('utf8');
    this.child.stderr!.on('data', (c: string) => { this.stderr = (this.stderr + c).slice(-8000); });
    this.child.on('error', (err: NodeJS.ErrnoException) => {
      this.finish(h, null, err.code === 'ENOENT'
        ? { message: `Claude Code CLI not found (${claudeBin()}).`, fix: 'Install Claude Code and sign in, or set MAMA_CLAUDE_BIN to its path, then restart the console.' }
        : { message: `Could not start Claude Code: ${err.message}`, fix: 'Check that `claude` runs in a terminal in this repo.' });
    });
    this.child.on('close', code => {
      this.finish(h, code, code === 0 || code === null ? undefined : explain(this.stderr));
    });
  }

  stop(): void {
    if (this.ended) return;
    this.child.kill('SIGINT');
    setTimeout(() => { if (!this.ended) this.child.kill('SIGTERM'); }, 5000).unref();
  }

  private finish(h: RunHandlers, code: number | null, error?: { message: string; fix?: string }) {
    if (this.ended) return;
    this.ended = true;
    h.onEnd(code, this.stderr, error);
  }
}

export function explain(stderr: string): { message: string; fix?: string } {
  const s = stderr.trim();
  if (/not logged in|login|authenticat|invalid api key|401/i.test(s)) {
    return { message: 'Claude Code is not signed in.', fix: 'Run `claude` in a terminal in this repo and sign in, then try again.' };
  }
  if (/No conversation found|session/i.test(s) && /resume/i.test(s)) {
    return { message: 'That chat session could not be resumed.', fix: 'Start a new chat.' };
  }
  const lastLine = s.split('\n').filter(l => l.trim() && !l.startsWith('⚠')).pop();
  return { message: lastLine || 'Claude Code stopped with an error.', fix: 'Run the same prompt in Claude Code to see the full output.' };
}
