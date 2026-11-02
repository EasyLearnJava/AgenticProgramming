"""
nimbus/constants.py: the app's fixed values: where its files are, the headers it reads and sends, the security headers
on every response, the chat's limits, and the model's caps. One place for each value, so the code and its tests always
agree.
"""

import logging
import re
from pathlib import Path
from typing import Final

# ① Where the app's files are, found from this file's place in the project, since the working directory can be
# anywhere: Vercel runs the app from the project's root, a test may run from elsewhere.
PROJECT_ROOT: Final = Path(__file__).resolve().parent.parent
DOCS_DIR: Final = PROJECT_ROOT / "docs"
DOCS_IMAGES_DIR: Final = DOCS_DIR / "images"
TEMPLATES_DIR: Final = PROJECT_ROOT / "templates"
# The stylesheet: Vercel's CDN serves public/ itself, so on Vercel the function never has this folder.
STATIC_DIR: Final = PROJECT_ROOT / "public" / "static"

# ② The request id: Vercel's own id for the request, when it looks like one, else a new one. Every log line carries
# it, and the browser gets it back in a header. ASCII only: Python's \w would also take any Unicode letter.
VERCEL_ID_HEADER: Final = "x-vercel-id"
REQUEST_ID_HEADER: Final = "x-request-id"
REQUEST_ID_PATTERN: Final = re.compile(r"[\w:.-]{1,128}", re.ASCII)
NEW_REQUEST_ID_CHARS: Final = 16

# ③ The security headers on every response the app makes; vercel.json gives the CDN's files the same ones. The
# Content Security Policy is enforced from the start: the pages load only our own stylesheet, scripts and pictures,
# and no other site may show them in a frame.
CONTENT_SECURITY_POLICY: Final = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ]
)
SECURITY_HEADERS: Final[tuple[tuple[str, str], ...]] = (
    ("content-security-policy", CONTENT_SECURITY_POLICY),
    ("x-content-type-options", "nosniff"),
    ("referrer-policy", "strict-origin-when-cross-origin"),
    ("x-frame-options", "DENY"),
    ("permissions-policy", "camera=(), geolocation=(self), microphone=()"),
)

# ④ The health check's answer is never cached: it says how the app is now; nor is an answer's stream.
NO_STORE: Final = "no-store"

# ⑤ The chat (step 2): what the form sends, and what comes back. A question is at most 2,000 characters; the body
# that carries it and the conversation so far (⑪), at most 256 KiB, room for both, each character of four UTF-8 bytes
# written %XX. The answer streams as server-sent events; our own error pages carry a header, so the page can tell them
# from anyone else's.
FORM_MEDIA_TYPE: Final = "application/x-www-form-urlencoded"
QUESTION_MAX_CHARS: Final = 2000
CHAT_BODY_MAX_BYTES: Final = 256 * 1024
CHAT_FORM_MAX_FIELDS: Final = 10
EVENT_STREAM: Final = "text/event-stream"
ERROR_HEADER: Final = "x-nimbus-error"

# ⑥ The visitor's locale and time zone, which the page sends with each question (step 3): a language tag such as
# "en-US", and a time zone of the IANA database such as "America/Chicago". Without them, the defaults.
DEFAULT_LOCALE: Final = "en-US"
DEFAULT_TIME_ZONE: Final = "UTC"
# A language tag: a language, then subtags of letters and digits (a script, a region, extensions such as -u-ca-...).
# Letters, digits and hyphens only, so nothing in it can read as an instruction in the system prompt.
LOCALE_PATTERN: Final = re.compile(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*", re.ASCII)
LOCALE_MAX_CHARS: Final = 35
# Where the units are imperial, by the locale's region: the United States, Liberia and Myanmar.
IMPERIAL_REGIONS: Final = frozenset({"US", "LR", "MM"})

# ⑦ The model (step 3): Gemini, through LangChain, capped. On Vercel, Stop never reaches the function (issue 32), so
# an answer no one reads still runs to its end: each answer is at most 1,024 tokens and 30 seconds, whatever happens;
# each call to Gemini waits at most 20 s, and a failed one is tried once more. For Gemini, LangChain's max_retries
# counts every attempt, the first one included (google-genai's HttpRetryOptions.attempts): two attempts, one retry
# (issue 36). Its thinking stays at the least there is, since thinking's tokens count against the 1,024.
GEMINI_MODEL: Final = "gemini-3.5-flash-lite"
MAX_OUTPUT_TOKENS: Final = 1024
ANSWER_TIMEOUT_SECONDS: Final = 30
MODEL_REQUEST_TIMEOUT_SECONDS: Final = 20
MODEL_MAX_ATTEMPTS: Final = 2
MODEL_THINKING: Final = "minimal"

# ⑧ Other libraries' own log lines (httpx's, google-genai's, LangSmith's): only their warnings and worse are written,
# as lines of ours. Their info lines name each request they send, a query string included (issue 43). Of an
# exception, its class and its innermost 8 frames.
LIBRARY_LOG_LEVEL: Final = logging.WARNING
LIBRARY_LOG_MAX_FRAMES: Final = 8

# ⑨ The weather (step 4): Open-Meteo's three APIs, asked with no key. A try waits at most 3 s; a slow or failed one
# gets one more, after a random wait of at most half a second; a 429 is tried again only when its Retry-After asks for
# at most 1.5 s.
OPEN_METEO_GEOCODING_URL: Final = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST_URL: Final = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_AIR_QUALITY_URL: Final = "https://air-quality-api.open-meteo.com/v1/air-quality"
OPEN_METEO_TRY_SECONDS: Final = 3
OPEN_METEO_ATTEMPTS: Final = 2
RETRY_WAIT_MAX_SECONDS: Final = 0.5
RETRY_AFTER_MAX_SECONDS: Final = 1.5
# What the tools take: a place's name of at most 100 characters; at most 10 places, 5 if the model doesn't say; a
# forecast of 1 to 16 days, with each hour of the first 3 if asked. A point is rounded to 2 decimals, about 1 km, so no
# request names an exact address.
MAX_QUERY_CHARS: Final = 100
DEFAULT_PLACE_COUNT: Final = 5
MAX_PLACE_COUNT: Final = 10
MAX_FORECAST_DAYS: Final = 16
MAX_HOURLY_DAYS: Final = 3
COORDINATE_DECIMALS: Final = 2

# ⑩ The agent (step 5): a LangGraph graph of our own, its tools on the lane the question takes (nimbus/lanes.py). At
# most 5 calls to the model in an answer, the fifth with its tools turned off, so every answer ends in words; each
# call's first words within 10 s; each tool call within 8 s, its tries included; the whole answer within 30 s (⑦).
# LangGraph's recursion limit stays as a backstop: it counts each node's run, a model call or a round of tools, so
# twice the calls.
AGENT_NAME: Final = "nimbus"
MAX_MODEL_CALLS: Final = 5
MODEL_FIRST_CHUNK_SECONDS: Final = 10
TOOL_TIMEOUT_SECONDS: Final = 8
AGENT_RECURSION_LIMIT: Final = 2 * MAX_MODEL_CALLS

# ⑪ The chat's memory (step 6): the page sends back the conversation so far with each question, as untrusted input:
# only the visitor's questions and Nimbus's answers, in turns, never a tool's result, so the tools run again. At most
# the last 10 messages, each question 2,000 characters and each answer 4,000, all of them at most 16,000.
HISTORY_MAX_MESSAGES: Final = 10
HISTORY_ANSWER_MAX_CHARS: Final = 4000
HISTORY_MAX_CHARS: Final = 16000

# ⑫ The weather's cache (step 7): Open-Meteo's answers, kept in Vercel's Runtime Cache, which on Hobby all of a team's
# projects share: under our own namespace. A place's name and point hardly change: 30 days. A forecast, 30 minutes,
# but never past the place's midnight, since its first day is the day it was fetched; the air, 30 minutes; the weather
# now, 10. A read or a write that takes more than 1 s is given up, as a miss: the package itself would wait 30 s.
CACHE_NAMESPACE: Final = "nimbus-weather"
CACHE_TIMEOUT_SECONDS: Final = 1
SECONDS_PER_DAY: Final = 24 * 60 * 60
GEOCODING_CACHE_SECONDS: Final = 30 * SECONDS_PER_DAY
FORECAST_CACHE_SECONDS: Final = 30 * 60
CURRENT_CACHE_SECONDS: Final = 10 * 60
AIR_QUALITY_CACHE_SECONDS: Final = 30 * 60

# ⑬ Our MCP server (step 8), at /api/mcp: the same four weather tools, for any MCP client. It keeps no session, since
# Vercel's copies share no memory, and answers in JSON, not a stream. A request's body is at most 8 KiB: a tool call's
# input takes a few hundred bytes. On a computer, a request must name the app as 127.0.0.1 or localhost, with a port
# or without one (issue 62).
MCP_PATH: Final = "/api/mcp"
MCP_SERVER_NAME: Final = "nimbus-weather"
MCP_BODY_MAX_BYTES: Final = 8 * 1024
MCP_LOCAL_HOSTS: Final = ("127.0.0.1", "localhost", "[::1]", "127.0.0.1:*", "localhost:*", "[::1]:*")

# ⑭ The MCP · no auth lane (step 9): the agent's tools call our own MCP server, on this same deployment. Connecting to
# it and listing its tools take at most 6 s together; each call, 8 s, as on REST (⑩). If Vercel's protection guards
# the deployment's own address, the secret that gets an automated call past it goes in this header.
MCP_CONNECT_SECONDS: Final = 6
BYPASS_HEADER: Final = "x-vercel-protection-bypass"

# ⑮ The lanes with auth (step 10): get_forecast through Apify's Actor, behind Apify's token. Over REST, one request
# runs the Actor and answers with its items; over MCP, Apify's MCP server, with call-actor, then get-dataset-items, at
# most 100 items in one read (an hourly forecast has 72). Both pin the Actor's build, stop its run at 18 s and its
# charge at $0.01. An answer on these lanes has 50 s; the Actor's call, 20 s; connecting to Apify's MCP server, 5 s. A
# call that fails falls back to its twin with no auth only with 12 s of the answer left, for the twin's 8 s and the
# words. Apify's own words about a failure are cut to 200 characters.
APIFY_ACTOR_RUN_URL: Final = (
    "https://api.apify.com/v2/acts/gochujang~open-meteo-weather-forecast/run-sync-get-dataset-items"
)
APIFY_ACTOR_BUILD: Final = "1.0.9"
APIFY_RUN_TIMEOUT_SECONDS: Final = 18
APIFY_MAX_CHARGE_USD: Final = 0.01
APIFY_MCP_URL: Final = "https://mcp.apify.com/?tools=call-actor,gochujang/open-meteo-weather-forecast"
APIFY_ACTOR: Final = "gochujang/open-meteo-weather-forecast"
ACTOR_TOOL_NAME: Final = "gochujang--open-meteo-weather-forecast"
APIFY_RUN_TOOL: Final = "call-actor"
APIFY_DATASET_TOOL: Final = "get-dataset-items"
MAX_ACTOR_ITEMS: Final = 100
AUTH_ANSWER_TIMEOUT_SECONDS: Final = 50
AUTH_TOOL_SECONDS: Final = 20
APIFY_MCP_CONNECT_SECONDS: Final = 5
FALLBACK_MIN_LEFT_SECONDS: Final = 12
MAX_APIFY_DETAIL_CHARS: Final = 200
# A run costs about half a cent, capped at one, and anyone can ask (issue 66): at most 2 runs an answer, and 25 a day
# across the app, counted in the weather's cache; past either, the forecast falls back with no run.
APIFY_RUNS_PER_ANSWER: Final = 2
APIFY_RUNS_PER_DAY: Final = 25

# ⑯ Monitoring (step 12): Axiom's US edge, where the dataset's organisation is; a batch of lines has 2 s, and at most
# 1,000 lines wait for one. Sentry has the same 2 s to send what it has, at the same moment.
AXIOM_INGEST_HOST: Final = "us-east-1.aws.edge.axiom.co"
AXIOM_SEND_SECONDS: Final = 2
AXIOM_MAX_WAITING_LINES: Final = 1000
SENTRY_SEND_SECONDS: Final = 2

# ⑰ The health check (step 12): four checks at once, 8 s each, none of which costs; Open-Meteo geocodes Paris, its
# cache skipped; Apify's REST door reads the account behind the token. A run's report answers the same address for a
# minute; Vercel's CDN keeps a 200 for one more, and a browser keeps nothing.
HEALTH_CHECK_SECONDS: Final = 8
HEALTH_PLACE: Final = "Paris"
HEALTH_RUN_SECONDS: Final = 60
HEALTH_CACHE_CONTROL: Final = "public, max-age=0, s-maxage=60"
APIFY_ME_URL: Final = "https://api.apify.com/v2/users/me"

# ⑱ The Observability pages (step 14): Axiom's query door, on the same edge as its ingest, asked with a token that
# can only query; each query has 5 s. The pages look back 7 days, and Activity shows the latest 50 lines. A page's
# queries answer it for a minute on each copy of the app, and Vercel's CDN keeps the page a minute more, as the health
# check's. The golden questions (step 13), and their last run, kept beside them; the source, on GitHub.
AXIOM_QUERY_URL: Final = f"https://{AXIOM_INGEST_HOST}/v1/query/_apl?format=tabular"
AXIOM_QUERY_SECONDS: Final = 5
OBSERVABILITY_DAYS: Final = 7
ACTIVITY_LINES: Final = 50
OBSERVABILITY_RUN_SECONDS: Final = 60
OBSERVABILITY_CACHE_CONTROL: Final = HEALTH_CACHE_CONTROL
GOLDEN_FILE: Final = PROJECT_ROOT / "evals" / "golden.json"
LAST_RUN_FILE: Final = PROJECT_ROOT / "evals" / "last-run.json"
SOURCE_URL: Final = "https://github.com/EasyLearnJava/AgenticProgramming/tree/main/projects/Agentic/weather-chatbot"
