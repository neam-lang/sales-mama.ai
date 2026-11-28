// Messages between the browser and the console server over the WebSocket.
import type { StreamEvent } from './stream';
import type { Book, TeamBook } from './book';
import type { MarketWindow, WindowStatus } from './window';

export interface Me {
  id: string;
  name: string;
  role: 'rep' | 'manager' | string;
  markets: string[];
  email: string;
}

export interface Rail {
  me: Me | null;
  book: Book | null;
  team: TeamBook | null;
  windows: WindowStatus[];
  markets?: Record<string, MarketWindow>;  // the user's markets from knowledge/markets.yaml, for live clocks
  allocation?: { path: string; date: string; leads: number } | null;  // manager: a proposal awaiting approval
  bookPath: string | null;
  problem?: string;       // e.g. "No rep profile for you@x.com: run /mama-setup"
}

export type ClientMsg =
  | { type: 'prompt'; text: string; sessionId?: string; voice?: boolean }   // voice: spoken in a live conversation (short answer first)
  | { type: 'stop' };

export type ServerMsg =
  | { type: 'rail'; rail: Rail }
  | { type: 'turn_start'; turnId: string; text: string }
  | { type: 'event'; turnId: string; event: StreamEvent }
  | { type: 'turn_end'; turnId: string; code: number | null; stderr: string; error?: { message: string; fix?: string } }
  | { type: 'busy' };
