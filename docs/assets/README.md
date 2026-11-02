# Assets

Images used by the top-level README and the meetup talk. All names and numbers come from the fictional demo data (`*.example` domains).

| File | What |
|---|---|
| `hero.png` | README banner |
| `poster.png` | Meetup poster (2400 × 3400, prints well at A4/A3) |
| `demo.gif`, `demo.mp4` | 36-second console tour: cockpit, book, source drawer, morning run |
| `screens/*.jpg` | Console screenshots (desktop at 1440 px, mobile at 390 px) |

## Regenerate
Screens and the GIF come from the console's **replay mode**, which renders recorded streams and never runs the CLI.

```bash
npm run console                                   # shell 1 → http://localhost:4173
npm i --no-save playwright-core && npx playwright install chromium
node docs/assets/src/tour.mjs /tmp/sm-tour        # stills in shots/, GIF frames in frames/
node docs/assets/src/render.mjs                   # poster.png and hero.png from src/*.html
```

`tour.mjs` replaces the local repo path with `~/sales-mama.ai` in what it captures. The ffmpeg line for the GIF is at the top of that file.
