#!/usr/bin/env node
// `npm run console` from the repo root: check Node, install once, start the server.
import { spawnSync, spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = join(dirname(fileURLToPath(import.meta.url)), '..');
const major = Number(process.versions.node.split('.')[0]);
if (major < 20) {
  console.error(`Sales Mama Console needs Node 20 or newer (you have ${process.versions.node}).\n` +
    'Install it from nodejs.org, or with nvm: `nvm install 20 && nvm use 20`.');
  process.exit(1);
}
if (!existsSync(join(dir, 'node_modules', 'tsx'))) {
  console.log('First run: installing console dependencies…');
  const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  const r = spawnSync(npm, ['install', '--no-audit', '--no-fund'], { cwd: dir, stdio: 'inherit', shell: process.platform === 'win32' });
  if (r.status !== 0) process.exit(r.status ?? 1);
}
const child = spawn(process.execPath, ['--import', 'tsx', 'server/index.ts'], { cwd: dir, stdio: 'inherit' });
child.on('exit', code => process.exit(code ?? 0));
for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => child.kill(sig));
