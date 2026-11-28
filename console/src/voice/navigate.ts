// Voice navigation helpers (spec §16). Each one does exactly what a click or a key already does in
// the console: no new powers, and nothing here writes or sends.

const thread = () => document.querySelector<HTMLElement>('.route-chat .thread');
const turnEls = () => Array.from(document.querySelectorAll<HTMLElement>('.route-chat .turn2'));

/** Scroll the chat. Scrolling up first tells stick-to-bottom that the reader moved (as a wheel would). */
export function scrollChat(to: 'up' | 'down' | 'top' | 'bottom') {
  const el = thread();
  if (!el) return;
  if (to === 'bottom') { window.dispatchEvent(new Event('mama:jump')); return; }
  el.dispatchEvent(new WheelEvent('wheel', { deltaY: -120, bubbles: true }));
  const page = el.clientHeight * 0.8;
  if (to === 'top') el.scrollTo({ top: 0, behavior: 'smooth' });
  else el.scrollBy({ top: to === 'up' ? -page : page, behavior: 'smooth' });
}

/** Bring answer i into view and mark it as the one in focus (a visible ring, and aria-current). */
export function focusTurn(i: number) {
  const els = turnEls();
  els.forEach((el, j) => { el.classList.toggle('voice-focus', j === i); if (j === i) el.setAttribute('aria-current', 'true'); else el.removeAttribute('aria-current'); });
  const el = els[i];
  if (!el) return;
  thread()?.dispatchEvent(new WheelEvent('wheel', { deltaY: -120, bubbles: true }));
  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

export function clearFocus() { turnEls().forEach(el => { el.classList.remove('voice-focus'); el.removeAttribute('aria-current'); }); }

/** Click numbered source n (0-based) of answer i. Returns the file name, or null if there is none. */
export function openSource(i: number, n: number): string | null {
  const el = turnEls()[i];
  if (!el) return null;
  let chips = Array.from(el.querySelectorAll<HTMLButtonElement>('.sources .src:not(.more)'));
  if (n >= chips.length) { el.querySelector<HTMLButtonElement>('.sources .src.more')?.click(); chips = Array.from(el.querySelectorAll<HTMLButtonElement>('.sources .src:not(.more)')); }
  const chip = chips[n];
  if (!chip) return null;
  chip.click();
  return chip.title.split('/').pop() ?? chip.title;
}

/** Click "Open in canvas" on answer i. */
export function openCanvas(i: number): boolean {
  const el = turnEls()[i];
  const btn = el && Array.from(el.querySelectorAll<HTMLButtonElement>('button')).find(b => /open in canvas/i.test(b.textContent ?? '') || /open in canvas/i.test(b.getAttribute('aria-label') ?? ''));
  if (!btn) return false;
  btn.click();
  return true;
}

/** Close whatever is open on top (drawer, canvas, palette, settings), as Esc or the close button does. */
export function closeTop() {
  const drawer = document.querySelector<HTMLElement>('.drawer-bg');            // source drawer: click outside closes it
  if (drawer) { drawer.click(); return; }
  const canvas = document.querySelector<HTMLButtonElement>('.canvas button[aria-label^="Close the canvas"]');
  if (canvas) { canvas.click(); return; }
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
}

/** Calendar keys: ← → t d w m (the calendar's own keyboard map). */
export function calendarKey(key: 'ArrowLeft' | 'ArrowRight' | 't' | 'd' | 'w' | 'm') {
  window.dispatchEvent(new KeyboardEvent('keydown', { key }));
}
