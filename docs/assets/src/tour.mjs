// Record the console tour (stills + GIF frames) from recorded streams. Never runs the CLI.
// Usage: npm run console (in another shell), then: node docs/assets/src/tour.mjs <out-dir>
// Then: ffmpeg -framerate 12 -i <out-dir>/frames/f%04d.png -vf "scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" docs/assets/demo.gif
import { chromium } from 'playwright-core';
import { mkdirSync, rmSync } from 'node:fs';
const exe = process.env.CHROME; // optional path to a Chromium binary
const OUT = process.argv[2]; const BASE = 'http://127.0.0.1:4173/';
rmSync(`${OUT}/frames`, { recursive: true, force: true }); mkdirSync(`${OUT}/frames`, { recursive: true }); mkdirSync(`${OUT}/shots`, { recursive: true });
const scrub = p => p.evaluate(() => {
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = w.nextNode());) n.nodeValue = n.nodeValue.replace(/\/Users\/[^/\s']+\/[^\s']*?sales-mama\.ai/g, '~/sales-mama.ai');
});
const b = await chromium.launch(exe ? { executablePath: exe } : {});

// ---------- stills (2x) ----------
const still = async (q, name, { w = 1440, h = 900, at, click } = {}) => {
  const p = await b.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 2 });
  await p.goto(BASE + q); await p.waitForTimeout(2500); await scrub(p);
  if (at) { await p.getByText(at, { exact: false }).first().evaluate(el => { const r = el.getBoundingClientRect(); window.scrollTo(0, window.scrollY + r.top - 110); }); }
  else await p.evaluate(() => window.scrollTo(0, 0));
  if (click) { await p.getByRole('button', { name: click }).first().click(); await p.waitForTimeout(900); await scrub(p); }
  await p.waitForTimeout(500);
  await p.screenshot({ path: `${OUT}/shots/${name}.png` }); await p.close();
};
await still('', 'empty');
await still('?replay=mama-manager', 'manager-run', { at: 'Last run · 2026-11-02' });
await still('?replay=mama-manager', 'manager-brief', { at: '1. Runner status' });
await still('?replay=mama-book', 'book', { at: "Praveen's book" });
await still('?replay=mama-book', 'source', { at: "Praveen's book", click: 'wiki/accounts/nimbus-clinics.md' });
await still('?replay=mama-day', 'day-plan', { at: 'mama-day · Mon 2 Nov' });
await still('?replay=mama-day', 'mobile-day', { w: 390, h: 844, at: 'Your day, Mon 2 Nov' });
await still('?replay=mama-manager', 'mobile-manager', { w: 390, h: 844, at: 'Allocation proposal · 2026-11-02' });

// ---------- GIF frames (1x) ----------
const p = await b.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
let f = 0; const snap = async (n = 1) => { for (let i = 0; i < n; i++) await p.screenshot({ path: `${OUT}/frames/f${String(f++).padStart(4, '0')}.png` }); };
const FPS = 12;
const hold = s => snap(Math.round(s * FPS));
const yOf = t => p.getByText(t, { exact: false }).first().evaluate(el => window.scrollY + el.getBoundingClientRect().top - 110);
const glide = async (to, s) => { const from = await p.evaluate(() => window.scrollY); const n = Math.round(s * FPS);
  for (let i = 1; i <= n; i++) { const k = i / n, e = k < .5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2; await p.evaluate(y => window.scrollTo(0, y), from + (to - from) * e); await snap(); } };
const load = async q => { await p.goto(BASE + q); await p.waitForTimeout(2500); await scrub(p); await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(300); };

// 1. empty state + typing (never submitted)
await load(''); await hold(1.2);
const box = p.locator('#composer'); await box.click();
for (const ch of '/mama-manager') { await box.type(ch); await snap(2); }
await hold(0.8);
// 2. manager cockpit
await load('?replay=mama-manager'); await hold(1.2);
await glide(await yOf('1. Runner status'), 1.4); await hold(1.6);
await glide(await yOf('2. Hot accounts'), 1.0); await hold(1.6);
await glide(await yOf('Last run · 2026-11-02'), 1.6); await hold(2.0);
await glide(await yOf('Allocation proposal · 2026-11-02'), 1.0); await hold(2.2);
await glide(await yOf('Team book · 2026-11-02'), 1.0); await hold(1.2);
// 3. rep book + grounded source chip
await load('?replay=mama-book'); await hold(0.8);
await glide(await yOf('Hot accounts and a next action'), 1.2); await hold(2.0);
await glide(await yOf("Praveen's book"), 1.2); await hold(1.6);
await p.getByRole('button', { name: 'wiki/accounts/nimbus-clinics.md' }).first().click(); await p.waitForTimeout(700); await scrub(p); await hold(2.6);
// 4. morning run plan
await load('?replay=mama-day'); await hold(0.6);
await glide(await yOf('mama-day · Mon 2 Nov'), 1.4); await hold(1.6);
await glide(await yOf('Your day, Mon 2 Nov'), 1.0); await hold(2.4);
console.log('frames', f, 'seconds', (f / FPS).toFixed(1));
await b.close();
