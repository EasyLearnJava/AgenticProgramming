# Step 2 · The Chat Page, From a Sample

**What this step built:** the chat page in the design you shared, drawn from a sample conversation: the bubbles, the
tool chips with their path labels and wire views, the weather card, the 2×2 lane picker and the compare view. Nothing
calls a model or a weather service yet; that starts in step 3.

> **Since step 3,** the chat is live, so the sample conversation is gone; the components, the lane picker and the
> compare view remain, and [step 3](step-3.md) says what changed.

## What you see

- **The sample conversation:** the plan's question, "Do I need an umbrella in Paris tomorrow afternoon?", answered with
  Open-Meteo's real data from 29 October 2026. The page says it's a sample.
- **The lane picker:** the four lanes as a 2×2, REST or MCP down the side, without or with auth across the top. Each
  lane says the build step that makes it live.
- **Tool chips:** one per tool call, above the answer: the tool, a short form of its input, the lane it went through
  and the host it called. Open one to see the request (On the wire), its input and its output. In this sample, it's
  the request each lane would send; the live lanes, from step 3, show the ones they really send.
- **Switch the lane, and the chips change:** on `MCP · no auth` the forecast call is a JSON-RPC message to our own MCP
  server; on `REST · with auth` it's a POST to Apify's REST API carrying `Authorization: Bearer <APIFY_TOKEN>`.
- **The weather card:** the place, the period, a bar per hour for the chance of rain, and the data's source.
- **Compare the four lanes:** the same forecast call through each lane, side by side.
- **The input:** shown, but switched off until step 3.

## How it works

### Where the sample comes from

- `lib/chat/sample-conversation.ts` holds the sample: the question, the answer, and for each tool call, how each lane
  would make it: the tool's name on that lane, its input, its output, and the request.
- It works out the whole conversation for each of the four lanes on the server, and `app/page.tsx` hands all four to
  the chat window. Switching lanes only shows another of the four: the browser picks one, it doesn't build them.

### The components

| Component | What it does |
|---|---|
| `components/chat-window.tsx` | The chat card, and the only component that keeps state (`"use client"`): the chosen lane, and whether the compare view is open. It runs in the browser, and so do the components it shows; they only draw what they're given |
| `components/lane-picker.tsx` | The 2×2 of radio buttons, inside a `<fieldset>`: the arrow keys move between lanes, and screen readers announce its legend |
| `components/chat-message.tsx` | One message: who and when, its tool chips, its text, its weather card |
| `components/tool-chip.tsx` | One tool call. It's an HTML `<details>` element, so it opens with a click, Enter or Space, even without JavaScript |
| `components/weather-card.tsx` | The forecast at a glance; each bar's value is written out, for screen readers too |
| `components/chat-input.tsx` | The question box and the location pin, switched off for now |
| `components/compare-grid.tsx` | The four lanes side by side |

### The rule the sample keeps

Within a pair, the destination, the tool and its input stay the same; only the door changes. The forecast call, as the
compare view shows it:

| Pair | REST door | MCP door |
|---|---|---|
| **No auth** | `GET https://api.open-meteo.com/v1/forecast?...` | `POST .../api/mcp`: a JSON-RPC `tools/call` for `get_forecast` |
| **With auth** | `POST https://api.apify.com/v2/acts/.../run-sync-get-dataset-items`, with the token | `POST https://mcp.apify.com/?tools=...`: a JSON-RPC `tools/call` that runs the Actor, with the same token |

A unit test, `tests/unit/chat/sample-conversation.test.ts`, holds the sample to it: both doors of a pair send the same
tool with the same input, and only the auth lanes carry a token.

### The shared pieces

- `lib/types.ts`: the shapes the page works with, such as `LaneId`, `ToolCallView`, `ForecastView` and `MessageView`.
- `lib/constants.ts`: the four lanes (door, auth, label, the step that makes each live) and their 2×2 order.
- `lib/utils.ts`: the first shared helpers: `toWireText`, which writes a request the way it goes over the wire, and
  `toHost`, which takes the host from a URL for the chips.

## The checks this step added

- **Unit tests** for the helpers, the lanes, and the sample's rule, including that a token goes to Apify and to no
  other host (18 in all, with step 1's).
- **End-to-end tests** with Playwright, in `tests/e2e/`. They run in a real browser, on a desktop screen and on a
  360-pixel phone screen, and check: the conversation; that a chip really opens and shows its request, and that it
  switches with the lane; the arrow keys in the lane picker; the compare view; the documentation and the 404 page;
  that nothing scrolls sideways; and an axe accessibility scan with no violations.
- They run against this laptop's build, or against a live site. CI runs them on every push, against its own build;
  after each deploy, they're also run by hand against https://weather-chatbot-hazel.vercel.app/ to check it.

```bash
npx playwright install chromium
npm run e2e
BASE_URL=https://weather-chatbot-hazel.vercel.app npm run e2e
```

The first command downloads Playwright's browser, once. In PowerShell, set the variable first
(`$env:BASE_URL = "https://weather-chatbot-hazel.vercel.app"`), then run `npm run e2e`. To use a browser that's already
installed instead, set `E2E_BROWSER_CHANNEL` (for example `msedge`).

## Files in this step

| File | What it does |
|---|---|
| `app/page.tsx` | The chat page: the chat window, with the sample |
| `app/globals.css` | The new styles: the chat card, lane grid, chips, weather card, input, compare view |
| `components/chat-window.tsx`, `lane-picker.tsx`, `chat-message.tsx`, `tool-chip.tsx`, `weather-card.tsx`, `chat-input.tsx`, `compare-grid.tsx` | The components above |
| `lib/chat/sample-conversation.ts` | The sample, worked out for each lane |
| `lib/types.ts`, `lib/constants.ts`, `lib/utils.ts` | The shared types, the lanes, the helpers |
| `docs/step-2.md` | This page |
| `tests/unit/utils.test.ts`, `tests/unit/constants.test.ts`, `tests/unit/chat/sample-conversation.test.ts` | The unit tests |
| `playwright.config.ts`, `tests/e2e/chat-page.spec.ts`, `tests/e2e/docs.spec.ts` | The end-to-end tests |
| `.github/workflows/weather-chatbot.yml` | CI now also runs the end-to-end tests |

## Check it yourself

From `projects/Agentic/weather-chatbot`:

```bash
npm install
npx playwright install chromium
npm test
npm run build
npm run e2e
npm run dev
```

Then open http://localhost:3000, open a tool chip, switch the lane, and open the compare view.

## What's next

**Step 3:** `REST · no auth`, the first live lane: the four weather tools, Open-Meteo's API, and the chat route with
Gemini. The input switches on.
