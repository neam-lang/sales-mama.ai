// Render the poster and hero banner to PNG with headless Chromium.
// Needs: npm i -g playwright-core (or a local install) and a Chromium from `npx playwright install chromium`.
// Usage: node docs/assets/src/render.mjs
import { chromium } from 'playwright-core';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, '..');
const browser = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
for (const [name, w, h] of [['poster', 1200, 1700], ['hero', 1600, 680]]) {
  const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 2 });
  await page.goto(pathToFileURL(join(here, `${name}.html`)).href, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: join(out, `${name}.png`) });
  console.log(`wrote docs/assets/${name}.png`);
}
await browser.close();
