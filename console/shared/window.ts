// Send-window status for the rail, from a market's entry in knowledge/markets.yaml,
// evaluated in that market's time zone.

export interface MarketWindow {
  tz: string;
  send_windows?: { days?: string[]; hours?: string };
  holidays?: (string | Date)[];
}

export interface WindowStatus {
  market: string;
  open: boolean;
  label: string;   // "Send window open · closes in 1h 20m"
  detail: string;  // "09:00–11:30 SGT · Mon–Thu"
}

function localParts(now: Date, tz: string) {
  const f = new Intl.DateTimeFormat('en-GB', {
    timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', weekday: 'short', hour12: false,
  });
  const p = Object.fromEntries(f.formatToParts(now).map(x => [x.type, x.value]));
  return {
    date: `${p.year}-${p.month}-${p.day}`,
    day: String(p.weekday).toLowerCase().slice(0, 3),
    minutes: (Number(p.hour) % 24) * 60 + Number(p.minute),
  };
}

const toMin = (hhmm: string) => { const [h, m] = hhmm.split(':').map(Number); return h * 60 + (m || 0); };
const dur = (min: number) => (min >= 60 ? `${Math.floor(min / 60)}h ${min % 60}m` : `${min} min`);
const isoDate = (d: string | Date) => (d instanceof Date ? d.toISOString().slice(0, 10) : String(d));

export function sendWindow(market: string, cfg: MarketWindow, now = new Date()): WindowStatus {
  const days = (cfg.send_windows?.days ?? []).map(d => d.toLowerCase().slice(0, 3));
  const [from = '09:00', to = '11:30'] = (cfg.send_windows?.hours ?? '09:00-11:30').split('-');
  const tzShort = new Intl.DateTimeFormat('en-GB', { timeZone: cfg.tz, timeZoneName: 'short' })
    .formatToParts(now).find(p => p.type === 'timeZoneName')?.value ?? cfg.tz;
  const span = days.length ? `${cap(days[0])}–${cap(days[days.length - 1])}` : 'no send days';
  const detail = `${from}–${to} ${tzShort} · ${span}`;
  const holidays = new Set((cfg.holidays ?? []).map(isoDate));
  const here = localParts(now, cfg.tz);
  const sendDay = (date: string, day: string) => days.includes(day) && !holidays.has(date);
  const start = toMin(from), end = toMin(to);

  if (sendDay(here.date, here.day) && here.minutes >= start && here.minutes < end) {
    return { market, open: true, label: `Send window open · closes in ${dur(end - here.minutes)}`, detail };
  }
  if (sendDay(here.date, here.day) && here.minutes < start) {
    return { market, open: false, label: `Send window opens in ${dur(start - here.minutes)}`, detail };
  }
  for (let i = 1; i <= 14; i++) {
    const next = localParts(new Date(now.getTime() + i * 86400000), cfg.tz);
    if (sendDay(next.date, next.day)) {
      const when = i === 1 ? 'tomorrow' : `${cap(next.day)} ${Number(next.date.slice(8))}`;
      const why = holidays.has(here.date) ? ' (holiday today)' : '';
      return { market, open: false, label: `Next send window ${when} ${from}${why}`, detail };
    }
  }
  return { market, open: false, label: 'No send window in the next 2 weeks', detail };
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
