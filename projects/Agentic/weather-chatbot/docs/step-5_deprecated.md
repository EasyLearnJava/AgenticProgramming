# Step 5 · Errors and Logs

**What this step built:** one error map for every failure, and logs you can follow. Each failure becomes one of a
fixed set of classes, which decides the sentence you see, how loudly it's logged and whether trying again can help.
Each request gets an id; every line it logs carries it, `/api/mcp` logs under the same id, and an error's sentence ends
with its last 8 characters, the ref, so its lines can be found.

## What you see

- **An error's sentence ends with its ref:** "The assistant didn't answer. Please try again. (ref b1a0d9e8)". Only the
  failures logged as errors carry one: the model failing, a setting missing, an answer we didn't expect, a bug.
  Trouble that passes, such as a slow or busy weather service, gets its sentence alone.
- **A bad tool call says so on its chip:** "The assistant called a weather tool the wrong way." Until this step, that
  chip said the assistant didn't answer (issues log, entry 54).
- **Open an MCP chip:** its request now carries `x-request-id`, the chat request's id.
- Everything else looks as before. The rest of this step is in the logs.

## How it works

### The error map

`lib/errors.ts` holds one class per kind of failure, and `toAppError()`, which turns anything thrown into one of
them, once: ours as they are; anything once the request says Stop; AI SDK's errors for a bad tool call; Gemini's own
failures, as AI SDK reports them (an HTTP error, its retries giving up, an error inside the stream, no answer at all);
and anything else, which is a bug, AI SDK's other errors included.

| Class | When | What you see | Level | Retry |
|---|---|---|---|---|
| `InputError` | A message breaks a rule: empty, too long, too many | The rule it broke | info | no |
| `ConfigError` | A setting is missing, such as `GOOGLE_API_KEY` | "The assistant isn't set up on this deployment yet." | error | no |
| `UpstreamTimeoutError` | Open-Meteo, or our MCP server, past its time budget | "The weather service took too long to answer." | warn | yes |
| `UpstreamUnavailableError` | Open-Meteo answers 5xx, or can't be reached | "The weather service can't be reached right now." | warn | yes |
| `UpstreamRateLimitedError` | Open-Meteo answers 429 | "The weather service is busy." | warn | yes |
| `ContractError` | Open-Meteo refuses the request, or answers in another shape | "The weather service answered in a way we didn't expect." | error | no |
| `ModelError` | Gemini fails: a 5xx, a timeout, the free tier's quota used up | "The assistant didn't answer. Please try again." | error | yes |
| `BadToolCallError` | The model calls a tool that doesn't exist, or with input it doesn't take | "The assistant called a weather tool the wrong way." | warn | yes |
| `AbortedError` | You press Stop, or close the page | Nothing | info | no |
| `UnexpectedError` | A bug | "Something went wrong." | error | no |

The page never gets an error's own text, a status code or a stack trace; the logs do (all but the stack trace, which
only a bug gets). "Retry: yes" means trying again can help: the retries themselves are Open-Meteo's second try and AI
SDK's own two, as before.

### One id per request

1. **The chat route** takes Vercel's own id for the request (the `x-vercel-id` header, such as
   `iad1::iad1::abcde-1730211234567-f3c2b1a0d9e8`), or makes one up on a laptop.
2. **Every line** the request logs carries it, as `requestId`, with the chat's id and the lane's three fields:
   `lane`, `transport` (`rest` or `mcp`) and `auth` (`none` or `bearer`).
3. **MCP · no auth sends it on** to `/api/mcp` as `x-request-id`. Each tool on our MCP server reads it from the request
   (`ctx.http.req`) and logs under it, so one id finds both functions' lines. The server is public, so any caller can
   send that header: its lines also carry `invocationId`, Vercel's own id for that request to `/api/mcp`.
4. **The page gets it back** in the response's `x-request-id` header, and as the ref at the end of an error's sentence.
   Search Vercel's logs for the ref to find the request.

### The lines a question writes

One line per event, as JSON, written by pino to stdout, which Vercel's logs show. The Paris question through
`MCP · no auth` writes:

| Line | Where | What it holds |
|---|---|---|
| `chat.request` | `/api/chat` | how many messages, the question's length (never its text), the locale |
| `lane.connect` | `/api/chat` | MCP only: how long connecting and listing the tools took, and how many tools |
| `tool.call` | `/api/chat` | each tool call, for every lane: the tool, its time, whether the cache answered |
| `mcp.call` | `/api/mcp` | the same call, as our MCP server saw it, for any MCP client, with its `invocationId` |
| `upstream.http` | where the tool ran | each request that went to Open-Meteo: the host, the status, the time, the tries |
| `model.step` | `/api/chat` | each model call: why it ended, its tokens, its tool calls |
| `chat.done` | `/api/chat` | the end: the time, the steps, the tool calls, the tokens |

An answer ends with one of five lines: `chat.done`; `chat.aborted` (Stop); `budget.exceeded` (a time budget cut it
short); `chat.failed` (it failed, at its class's level); or, before it starts, `chat.rejected` (a refused message).
Only one: after `chat.failed`, the page, which stops at the error, going away isn't logged as a stop too; and a lane
that fails to close writes `lane.close` (both since issue 96). When the page goes before any of them is written, the
answer's stream, at its end, writes `chat.aborted` (issue 101). Every line also names the build: `env`, `commit` and
`deploymentId`.

### Logged once, where it's handled

A failure is logged at its class's level once in each function, by the code that handles it: a failed tool call by
the chat (the model gets the error and answers anyway), a failure before the answer by the route (it answers with the
sentence), a failure on our MCP server by the server (it answers with an error result). The hops it passed on the way
write their usual line, saying it failed: `upstream.http` and `lane.connect` stay at info. So a slow Open-Meteo on
`REST · no auth` reads `upstream.http` failed, then `tool.call` at warn, then `chat.done`.

### What a line never holds

Your question's text, or a hash of it (hashing likely questions would find a short one): only its length. The
model's input to a tool it called wrongly: AI SDK's message for it quotes the input, so that line says what went wrong
in our own words, and names the tool only if it's one of ours. Tokens and keys (pino redacts any field that could hold
one), the bypass secret, and the chat id unless it's the kind useChat makes: letters, digits, `_` and `-`.

## Not in this step

- **Sentry**, which the plan had here, needs an account and a project key that only you can create; it comes with step
  9, with the other services that send the logs elsewhere (Axiom, alerts).
- **`AuthError` and `BudgetExceededError`** come with the auth lanes (step 6), the first code that can raise them;
  **`RateLimitedError` and `BotBlockedError`** with the protection (step 8).
- **The amber "slow, retrying" chip and the cached answer when Open-Meteo is down** come with the failure tests that
  exercise them (step 10).
- **The cost of an answer** waits for the paid model path (step 11); on the free tier, it's the quota.

## The checks this step added

- **The error map, played out** (`tests/unit/chat/error-map.test.ts`): each class triggered the way it happens in a
  chat turn, with what the page shows and the one line it logs; `tests/unit/app/api/chat/route.test.ts` plays
  `InputError` and `ConfigError`, which come before the answer starts.
- **The map itself** (`tests/unit/errors.test.ts`): each class's level and retry rule, which class anything becomes,
  and the ref.
- **The logger** (`tests/unit/logger.test.ts`): a line's fields, a child's fields, redaction, a failure's cause.
- **The lines of a whole turn** (`tests/unit/chat/run-chat.test.ts`), **of the MCP server**
  (`tests/unit/weather/register-tools.test.ts`, under the id the lane sent), and **of Open-Meteo's calls**
  (`tests/unit/upstream/open-meteo.test.ts`).
- **Request ids and the ref** (`tests/unit/utils.test.ts`).
- **An image in an answer's Markdown is never shown or fetched** (`tests/e2e/chat-page.spec.ts`): step 3's guard,
  which had no test until this step's bug stories.

## Files in this step

| File | What it does |
|---|---|
| `lib/errors.ts` | The error map: the classes, `toAppError()`, the sentence with its ref, the error response |
| `lib/logger.ts` | pino: the build's fields, redaction, the lane's fields, `logFailure()` |
| `app/api/chat/route.ts` | The request id, the first line and a failure's line before the answer starts |
| `lib/chat/run-chat.ts` | Each tool call's and model step's line, and how the answer ended |
| `lib/lanes/*.ts`, `lib/weather/register-tools.ts` | The logger passed on; `lane.connect`; `x-request-id` to `/api/mcp`; `mcp.call` |
| `lib/upstream/open-meteo.ts`, `lib/weather/tools/*.ts` | Each call takes its signal and logger together; `upstream.http` |
| `lib/chat/chat-request.ts` | The chat's id, checked, and the question being asked |
| `lib/config.ts`, `lib/constants.ts`, `lib/utils.ts` | `LOG_LEVEL` and the deployment's id; the headers; `toRequestId`, `toRef` |
| `tests/stubs/log-stand-ins.ts`, `tests/stubs/model-stand-ins.ts` | A logger whose lines a test reads; the mock model's steps |

## Check it yourself

From `projects/Agentic/weather-chatbot`:

```bash
npm test
npm run build
npm run e2e
```

Then, on the live site, ask a question and open Vercel's logs for the project (**Logs** in the project's dashboard):
each line of that answer has the same `requestId`, in `/api/chat` and, on `MCP · no auth`, in `/api/mcp` too.

## Checked on the live site

On 29 October 2026, once this step was live as `0943c74` (and its CI run had passed):

- **The request id, end to end.** An answer through `MCP · no auth` came back with `x-request-id:
  cle1::jnxr9-1793313250023-c454c392268a`, Vercel's own id for the request, and both of its MCP calls carried the same
  id to `/api/mcp`. A refused request (a body that isn't JSON) got its own id, and "That message can't be sent: its body
  isn't JSON.", without a ref, since a refusal isn't an error.
- **The lines, in Vercel's logs.** A search for that id found the answer's lines from both functions: `chat.request`,
  `lane.connect` (1,107 ms: the first connection after the deployment), a `tool.call`, an `mcp.call` and an
  `upstream.http` for each of the two tools, three `model.step` lines, and `chat.done`, the last line, written as the
  function ended, so pino's synchronous stream kept it. The refused request's `chat.rejected` line was there too.
  Vercel showed each `/api/mcp` line twice (issues log, entry 66).
- **No step went backwards.** The golden questions passed on both lanes (11 of 11, with the MCP server's own check),
  and the browser tests passed against the live site (44 of 44, once this laptop's network was back; the first run's
  three failures were `ERR_INTERNET_DISCONNECTED`).

## What's next

**Step 6:** `REST · with auth`: Apify's weather Actor through its REST API, with a token, and its fallback to
`REST · no auth`.
