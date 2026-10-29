# Step 4 · MCP · No Auth, Through Our Own MCP Server

**What this step built:** the second lane, and the plan's default. The same four weather tools now also live on our
own MCP server, at `/api/mcp`. On `MCP · no auth`, the chat route is an MCP client: it asks that server for the
tools, and the server calls Open-Meteo. Same tools, same data, same answers; only the door changes.

## What you see

- **The lane picker:** `MCP · no auth` is live and checked when a chat starts; `REST · no auth` is live too, and the
  arrow keys move between the two. The auth lanes stay switched off until steps 6 and 7.
- **The chips** of an answer on this lane say `MCP · no auth · weather-chatbot-hazel.vercel.app`: the host is this
  app itself, since our MCP server runs beside the chat.
- **Open a chip:** the request on the wire is a JSON-RPC `tools/call`, posted to `/api/mcp`, exactly as AI SDK's MCP
  client sent it: its headers name the method and the tool, and its body carries the input the model chose.
- **Compare the four lanes:** the `MCP · no auth` cell now shows that real request too.

## How it works

### One question, through MCP

1. The page posts your question to `/api/chat`, as before, now with `laneId: "mcp-no-auth"`.
2. **The route opens the lane** (`lib/lanes/mcp-no-auth.ts`): an MCP client (`@ai-sdk/mcp`) connects to `/api/mcp` on
   this same deployment, at the address the question came to, so a preview talks to its own server. Connecting and
   listing the tools have 3 s together.
3. **It checks the list:** the server must offer our four tools. A tool the server adds never reaches the model, and
   a missing one is a `ContractError`.
4. **The model calls tools** as on REST. Each call becomes a JSON-RPC `tools/call` to `/api/mcp`, where
   `app/api/mcp/route.ts` runs the very tool definition REST · no auth runs, against Open-Meteo.
5. **The answer streams back,** and the lane's connection is closed however it ends: finished, stopped or failed.

### One set of tools, two doors

`lib/weather/register-tools.ts` puts the four definitions from `lib/weather/open-meteo-tools.ts` on the MCP server
(with `mcp-handler`), the same list `REST · no auth` turns into AI SDK tools. Each MCP answer carries:

| Part | What's in it | Who uses it |
|---|---|---|
| `structuredContent` | the tool's output: the weather, in our names | the model, through the lane |
| `content` (text) | the one-line summary, such as "Paris, Île-de-France Region, FR · 48.85, 2.35" | the chip, and any MCP client |
| `_meta` | the request to Open-Meteo, and whether the cache answered | the lane, for the chip's "cached" mark |
| `isError` and `_meta.errorClass` | when a tool fails: our message, and its error class by name | the lane turns it back into the same class as on REST |

The tools are marked read-only (`readOnlyHint`), and as reaching outside (`openWorldHint`).

### What MCP adds on the wire

AI SDK's MCP client and `mcp-handler` speak MCP's 2026-07-28 version, which keeps no session:

- **The handshake is one request,** `server/discover`, then `tools/list`; the 2025 version's `initialize` is gone (the
  server still answers 2025-era clients).
- **Each request names itself** in its headers: `mcp-method: tools/call`, `mcp-name: get_forecast`,
  `mcp-protocol-version: 2026-07-28`; and carries the client's name and capabilities in the body's `_meta`.
- So one question costs three requests to `/api/mcp` before the first tool runs, where REST · no auth costs none:
  that hop is what the compare view is about, and what `tests/evals/mcp-server.eval.ts` times on the live site.
- **A cached answer still makes the call:** the `tools/call` goes out, and the server answers from its cache without
  asking Open-Meteo; the chip says "cached", and keeps the call's time.

### Measured on the live site

One run each, on 29 October 2026, once this step was live; so read them as sizes, not a benchmark.

| What | Time | Measured by |
|---|---|---|
| Connecting: `server/discover` | 192 ms | `tests/evals/mcp-server.eval.ts`, from a laptop |
| Listing the tools: `tools/list` | 78 ms | the same run |
| Three `tools/call` requests | 166, 98 and 97 ms | the same run |
| A tool call in a chat answer, through MCP, with Open-Meteo asked | 544 ms (geocoding), 446 ms (forecast) | the chips of one live answer to the Paris question |

So from a laptop, a request to `/api/mcp` takes about 100 ms before any tool runs, and a question pays for two of
them (connecting, then the tool list) before its first tool call.

### Where it connects, and the bypass secret

The lane calls `/api/mcp` on this same deployment (`toSelfOrigin` in `lib/lanes/open-lane.ts`): at the address the
chat request came to, if that's one of the deployment's own, as Vercel lists them (its URL, its branch's, the project's
production domain); otherwise at the deployment's own URL, so a forged `Host` header can't send the call elsewhere. On
a laptop, it's the request's own address. If the project has Protection Bypass for Automation on, Vercel sets
`VERCEL_AUTOMATION_BYPASS_SECRET`, and the lane sends it as `x-vercel-protection-bypass`, which gets a call to a
protected address (a preview, or the deployment's own URL) through. It isn't MCP auth, and the wire view masks it.

Vercel names one production domain (`VERCEL_PROJECT_PRODUCTION_URL`, the shortest). If a custom domain is ever added,
chats through the other production address (such as `weather-chatbot-hazel.vercel.app`) fall back to the deployment's
own URL, which Standard Protection guards: so turn on Protection Bypass for Automation along with adding the domain.

### What the public server accepts

`/api/mcp` is open to anyone, so `lib/weather/mcp-request.ts` checks each request before the MCP server sees it: one
JSON-RPC message at a time (a batch could carry up to 100 tool calls in one request, past any per-request rate
limit), of at most 8 KB; anything else gets a JSON-RPC error with `400` or `413`. A tool that fails for a reason that
isn't ours sends a fixed sentence, never the error's own text.

### Use the server from any MCP client

The server is public on purpose: it's the no-auth lane. Any MCP client that speaks Streamable HTTP can use it, for
example in Claude or Cursor:

```json
{ "nimbus-weather": { "url": "https://weather-chatbot-hazel.vercel.app/api/mcp" } }
```

## The checks this step added

- **The MCP server, through a real MCP client** (`tests/unit/weather/register-tools.test.ts`), in this process: it
  lists exactly our four tools, each with our own input schema (the contract test: a changed schema fails it), answers
  a call with structured content, a summary and `_meta`, and a failure with its class.
- **The lane** (`tests/unit/lanes/mcp-no-auth.test.ts`): the four tools, the `tools/call` request it really sent, the
  bypass secret sent and never shown, a server failure turned into the same class as on REST, and giving up on a
  server that doesn't connect within 3 s.
- **A whole chat turn through MCP**, with the mock model: both chips say `mcp-no-auth`.
- **The route** (`tests/unit/app/api/mcp/route.test.ts`) answers an MCP client as `nimbus-weather`.
- **End-to-end:** the default lane, the arrow keys between the live lanes, and an answer through MCP whose chip shows
  its JSON-RPC request.
- **Against a deployment** (`npm run evals`): the golden questions on each live lane (`EVAL_LANES`), and
  `tests/evals/mcp-server.eval.ts`, which connects to `/api/mcp` as any MCP client would, lists and calls the tools,
  and times the handshake and the calls.

```bash
EVAL_BASE_URL=https://weather-chatbot-hazel.vercel.app npm run evals
```

## Files in this step

| File | What it does |
|---|---|
| `app/api/mcp/route.ts`, `lib/weather/mcp-request.ts` | Our MCP server, at `/api/mcp`, and what it accepts |
| `lib/weather/register-tools.ts` | Puts the four tools on the MCP server |
| `lib/lanes/mcp-no-auth.ts` | MCP · no auth: the MCP client, the tool list check, each call and its record |
| `lib/lanes/open-lane.ts`, `app/api/chat/route.ts` | Opening a lane: this deployment's own address (`toSelfOrigin`), and waiting for MCP to connect |
| `lib/constants.ts`, `lib/types.ts` | Two live lanes, `MCP · no auth` the default; the MCP server's name and budgets |
| `lib/config.ts` | Reads the bypass secret Vercel sets |
| `lib/errors.ts`, `lib/utils.ts` | An error class from its name; `once()`, so a lane closes once |
| `lib/chat/lane-examples.ts` | The compare view's MCP · no auth request, as it's really sent |
| `tests/stubs/mcp-stand-ins.ts` and the tests above | Our MCP server in the test's own process |

## Check it yourself

From `projects/Agentic/weather-chatbot`:

```bash
npm test
npm run build
npm run e2e
```

Then, on the live site, ask the Paris question with `MCP · no auth` checked, and again with `REST · no auth`: the same
tools, the same answer, and in each chip, a different door.

## What's next

**Step 5:** errors and logs: the full error map, request ids passed on to `/api/mcp` (so one id finds both functions'
logs), and the logger with its lane fields and redaction.
