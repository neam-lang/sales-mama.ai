# Design

The target look for the optional Sales Mama Console (`docs/UI.md`, Phase 9): colourful, agentic and chat-driven.

| Screen | File | What it shows |
|---|---|---|
| Rep · Morning run | `canvas/Main.dc.html` | `/mama-day` with a live plan, agent lanes, summary tiles, a draft card and a bento side rail |
| Rep · Ask my book | `canvas/RepBook.dc.html` | The rep's book returned as a card: capacity, meetings ring, tier mix, next best actions, pipeline |
| Rep · Account brief | `canvas/Account.dc.html` | Score donut, signals timeline with sources, signal → pain → product → proof chain, VAM notes |
| Manager · Cockpit | `canvas/Manager.dc.html` | Nightly run status, allocation proposal with Approve, entity-match review queue, team book |
| Rep · On the go | `canvas/Mobile.dc.html` | Phone layout of the morning run |

The live, editable canvas is the "Sales Mama UI" design artifact in the owner's Claude account. These `.dc.html` files are its source: each is a design-component page that renders inside that canvas editor, not in a plain browser. Use them as the reference for layout, copy and tokens when building the console.

Design tokens (colours, type, shape) are listed in `docs/UI.md` §4. All names and numbers in the screens are sample data.
