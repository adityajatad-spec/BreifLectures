# BriefLectures for Chrome

Skips the filler in YouTube lectures, right in YouTube's own player. A panel under the video
shows the cut picker, a timeline of what plays and what's skipped, and the AI's progress.

It works with the BriefLectures Mac app: the app's engine reads and labels the lecture on your
Mac (any language, local AI), and the extension talks to it on `127.0.0.1:47913`. Nothing is
sent anywhere else. Without the app running, the panel says so and links to the download.

## Try it

```sh
make extension          # or: cd extension && npm install && npm run build
```

Then in Chrome: **chrome://extensions** → turn on **Developer mode** → **Load unpacked** →
choose `extension/dist`. Open the BriefLectures app, then any YouTube lecture.

## Publish to the Chrome Web Store

Each GitHub release includes `BriefLectures-chrome-extension.zip`.

1. Register at the [Chrome Web Store developer dashboard](https://chrome.google.com/webstore/devconsole) (one-time $5 fee).
2. **New item** → upload the zip.
3. Fill in the listing (description, screenshots, the 128 px icon from `icons/`), and the
   privacy section: the extension stores your cut and auto-skip choices, and sends the
   YouTube video ID to the BriefLectures app on your own computer. No data leaves the device.
4. Justify the permissions: `storage` (your settings) and access to `127.0.0.1` (the local app).
5. Submit for review. It usually takes a few days.

## How it fits together

- `src/content.ts`: runs on youtube.com. Follows YouTube's page changes, asks the engine to
  analyze the video, renders the panel (in a shadow root, so YouTube's CSS can't affect it),
  and skips ranges in the `<video>`. It never skips while an ad is playing.
- `src/background.ts`: finds the engine (port 47913, or 8000 for `make dev`) and relays
  requests to it; extension workers can reach 127.0.0.1 without CORS limits.
- The cut logic is shared with the app (`web/src/lib/cuts.ts`), so both skip exactly the same parts.
