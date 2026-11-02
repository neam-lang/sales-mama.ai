// Record a real stream for the parser tests: `npm run record -- mama-day`
// Runs exactly what the console runs (same args, same project permissions) and saves
// the stdout JSONL to test/fixtures/<name>.jsonl.
import { spawn } from 'node:child_process';
import { createWriteStream } from 'node:fs';
import { join } from 'node:path';
import { buildArgs, claudeBin } from '../server/engine';
import { findRepoRoot } from '../server/repo';

const skill = process.argv[2];
if (!skill || !/^[a-z0-9-]+$/.test(skill)) {
  console.error('Usage: npm run record -- <skill> [prompt]   e.g. npm run record -- mama-book');
  process.exit(2);
}
const prompt = process.argv.slice(3).join(' ') || `/${skill}`;
const root = findRepoRoot(process.cwd());
const out = join(root, 'console', 'test', 'fixtures', `${skill}.jsonl`);
const child = spawn(claudeBin(), buildArgs(prompt), { cwd: root, stdio: ['ignore', 'pipe', 'inherit'] });
child.stdout.pipe(createWriteStream(out));
child.on('close', code => { console.log(`${out} (exit ${code})`); process.exit(code ?? 1); });
