# Assets

Images used by the top-level README and the meetup talk. `demo.mp4` is for slides and local playback: GitHub does not play video files stored in a repo (only videos uploaded through its editor). All names and numbers come from the fictional demo data (`*.example` domains).

| File | What |
|---|---|
| `logo.png` | Square logo (512 × 512, transparent corners) |
| `social-preview.png` | GitHub social preview (1280 × 640). Upload in repo **Settings → General → Social preview** |
| `hero.png` | README banner |
| `architecture-light.svg`, `architecture-dark.svg` | Animated "How it works" infographic (slow; stops under reduced motion). Icons: Lucide, ISC |
| `poster.png` | Meetup poster (2400 × 3400, prints well at A4/A3) |
| `send-demo.gif` | Just the `/mama-send` replay: preview, approve, email + WhatsApp sent |
| `send-review.png` | Send review: real `send.py` output on the demo data (fake transport) |
| `demo.gif`, `demo.mp4` | Console tour, then a replay of a real `/mama-send` run (`src/send-demo.html`): one email and one WhatsApp approved and sent, demo data, fake transport |
| `screens/*.jpg` | Console screenshots (desktop at 1440 px, mobile at 390 px) |

## Regenerate
Screens and the GIF come from the console's **replay mode**, which renders recorded streams and never runs the CLI.

```bash
npm run console                                   # shell 1 → http://localhost:4173
npm i --no-save playwright-core && npx playwright install chromium
node docs/assets/src/tour.mjs /tmp/sm-tour        # stills in shots/, GIF frames in frames/
node docs/assets/src/render.mjs                   # poster, hero, logo, social preview, send review from src/*.html
npm i --no-save lucide-static@0.460.0
python3 docs/assets/src/architecture.py node_modules/lucide-static/icons   # the two architecture SVGs
```

`tour.mjs` replaces the local repo path with `~/sales-mama.ai` in what it captures. The ffmpeg line for the GIF is at the top of that file.
