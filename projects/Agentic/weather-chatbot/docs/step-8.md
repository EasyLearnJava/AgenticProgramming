# Step 8 · Protection: BotID and the Security Headers

**What this step built:** two of the protections in the plan's section 9.4. BotID's invisible check now guards the
chat's `POST /api/chat`: the page answers a challenge with each message, and the route refuses a request with no
browser behind it, before any work. And every response carries the security headers. The third protection, two
firewall rules (a bypass for our own traffic, then a rate limit), lives in Vercel's dashboard, not in code: you set
it, as the README's "Deploy it on Vercel" says.

## What you see

- **Nothing new on the page.** BotID asks you nothing: each message the page sends carries BotID's answer in its
  headers (`x-is-human`, `x-path`, `x-method`), added by BotID's script.
- **A script that posts to `/api/chat` is refused,** with `403` and "We couldn't verify this browser. Please reload the
  page." Its line is `chat.rejected`, at warn, with `BotBlockedError`; BotID writes a plain line of its own too, saying
  the request carried no answer to its challenge.
- **Every response carries the headers** below.

## How it works

### BotID, on Vercel only

1. **The page:** `instrumentation-client.ts` runs before the app and starts BotID for `POST /api/chat` (`initBotId`,
   from `botid/client/core`). BotID wraps the page's `fetch`: before a protected request goes out, it loads its
   challenge script from a path on our own origin that Vercel serves, and adds its answer to the request's headers.
2. **The route:** `checkBotId()` (from `botid/server`) runs first in `POST`, before the body is read. If it finds no
   browser behind the request, the request ends with `BotBlockedError`: `403`, our sentence, and `chat.rejected`. It
   gets 3 s, and the request's own signal: if BotID can't answer, the request goes on, and a `botid.failed` line, at
   warn, says so. The rate limit still holds, and BotID's trouble mustn't stop the chat (entry 107).
3. **Basic mode,** free on every plan. Deep Analysis, which scores thousands of signals, is a paid option on Pro.
4. **Only on Vercel.** Vercel serves BotID's challenge, and `checkBotId()` needs Vercel's OIDC token: away from Vercel
   it throws. So both sides read one switch, `isBotIdOn()` in `lib/botid.ts`: `NEXT_PUBLIC_BOTID`, which
   `next.config.ts` sets when the app is built, "on" only where Vercel sets `VERCEL=1`, and which Next.js writes
   into the page's code and the route's alike, so they can't disagree. On a laptop and in CI, the chat and the browser
   tests run as before (issues log, entries 103 and 106).

### The security headers

On every response, from `next.config.ts`:

| Header | Value | Why |
|---|---|---|
| `Content-Security-Policy-Report-Only` | our own scripts, styles, images, fonts and requests; no framing, plugins or other form targets | it reports what it would block, for now |
| `X-Content-Type-Options` | `nosniff` | a browser doesn't guess a file's type |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | other sites see our origin, not a page's full address |
| `X-Frame-Options` | `DENY` | no other site can frame ours, while the policy only reports |
| `Permissions-Policy` | `camera=(), geolocation=(self), microphone=()` | the location pin for our own page only; no camera, and no microphone until step 13's voice input |

The Content Security Policy only reports at first. Next.js's pages carry inline scripts and styles (hence
`'unsafe-inline'`), and BotID loads a script whose own needs aren't documented: a policy that blocked it would stop
the chat. So it's enforced once the live site shows it reports nothing we need (entry 104); meanwhile a browser test
fails on any report the chat, a chip, the compare view or the docs give (entry 108). Its first run found one: zod,
which checks the chat's messages in the page, probes for `new Function` to build faster parsers, and the policy reports
the probe. So the page's zod runs without them (`jitless`, in `instrumentation-client.ts`; entry 110).

### The firewall rules, set in Vercel's dashboard

Two custom rules, in this order (Hobby allows three custom rules, one of which may rate-limit):

1. **Bypass:** a request whose `x-vercel-protection-bypass` header is the project's bypass secret skips every later
   rule, and BotID. The chat's own calls to `/api/mcp` carry that header, so they're never limited; a script you run
   with the secret, such as the evals, gets past BotID.
2. **Rate limit:** `/api/*`, 20 requests a minute per IP address, then `429`. Without rule 1, every chat's calls to
   `/api/mcp`, which come from Vercel's own addresses, would count against one limit.

## Not in this step

- **Enforcing the Content Security Policy,** once the live check has read its reports.
- **Checking the firewall rules** (the 21st request in a minute gets `429`, the chat's own calls to `/api/mcp` don't),
  once you've set them.
- **Deep Analysis,** a paid option on Pro.

## The checks this step added

- **The chat route** (`tests/unit/app/api/chat/route.test.ts`): on Vercel, a request BotID finds no browser behind is
  refused with `403` before its body is read, and logged as `chat.rejected`; one it trusts goes on to the usual checks;
  and one BotID can't answer goes on too, with a `botid.failed` line.
- **The switch** (`tests/unit/next-config.test.ts`, `tests/unit/instrumentation-client.test.ts`): BotID on for an app
  built on Vercel and off elsewhere, and the page starting it for the chat's `POST` only when it's on.
- **The headers** (`tests/unit/next-config.test.ts`): on every response, with the policy's main rules.
- **`untilAborted()`** (`tests/unit/utils.test.ts`): a call's outcome, or the signal's reason once it fires.
- **In the browser** (`tests/e2e/chat-page.spec.ts`): the Content Security Policy reports nothing through an answer, a
  chip, the compare view, and three documentation pages.

## Files in this step

| File | What it does |
|---|---|
| `instrumentation-client.ts` | BotID's page side, started on Vercel only; the page's zod without `new Function` |
| `app/api/chat/route.ts` | BotID's check, before anything else |
| `lib/botid.ts`, `lib/errors.ts`, `lib/utils.ts`, `lib/constants.ts` | BotID's one switch; `BotBlockedError` (`403`); `untilAborted()`; BotID's 3 s |
| `next.config.ts` | The security headers; `NEXT_PUBLIC_BOTID` for the page |
| `biome.json` | Environment variables' names allowed as keys in `next.config.ts` and its test |
| `package.json` | `botid` 1.5.12 |

## Check it yourself

From `projects/Agentic/weather-chatbot`:

```bash
npm test
npm run build
npm run e2e
```

On the live site, `curl -sI https://weather-chatbot-hazel.vercel.app/` lists the headers, and a `POST` to `/api/chat`
from `curl` gets `403`. The chat page itself works as before.

## What's next

The policy enforced, once its reports are read; the firewall rules checked, once you've set them; then **step 9:**
observability.
