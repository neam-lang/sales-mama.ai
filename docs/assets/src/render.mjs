// Render the poster, hero banner, logo and GitHub social preview to PNG with headless Chromium.
// Needs: npm i -g playwright-core (or a local install) and a Chromium from `npx playwright install chromium`.
// Usage: node docs/assets/src/render.mjs
import { chromium } from 'playwright-core';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, '..');
const browser = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
for (const [name, w, h, dpr = 2] of [['poster', 1200, 1700], ['hero', 1600, 680], ['logo', 512, 512, 1], ['social', 1280, 640, 1], ['send-review', 1600, 900]]) {
  const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: dpr });
  await page.goto(pathToFileURL(join(here, `${name}.html`)).href, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  const file = `${name === 'social' ? 'social-preview' : name}.png`;
  await page.screenshot({ path: join(out, file), omitBackground: name === 'logo' });
  console.log(`wrote docs/assets/${file}`);
}
await browser.close();
