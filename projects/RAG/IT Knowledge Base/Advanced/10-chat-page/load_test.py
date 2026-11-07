"""
IT Knowledge Base: A Load Test
==============================

Sends questions to a running API from many threads at once, to check that the rate limit holds and the server stays
responsive while it's busy. It handles:
  1. --clients threads, each asking the question over and over for --seconds, all with one key
  2. Meanwhile, /health/live every half second: how long the server takes to answer anyone while it's busy
  3. The report: each status's count, the answers' and the health checks' times (median and 95th percentile), and
     whether the rate limit held: no more answers than the limit lets one caller have in that time

Only the standard library, so it runs anywhere Python does. A repeated question is answered from the engine's cache
after the first time: the load is on the API's own layers, not on the model's quota.

Usage (with the server running: python main.py):
    python load_test.py --key kb_... --clients 20 --seconds 20
"""
import argparse
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load the API from many threads; check the rate limit holds.")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="the API (default: http://127.0.0.1:8000)")
    parser.add_argument("--key", required=True, help="an API key (python main.py add-key NAME)")
    parser.add_argument("--clients", type=int, default=20, help="threads asking at once (default: 20)")
    parser.add_argument("--seconds", type=float, default=20.0, help="how long to keep asking (default: 20)")
    parser.add_argument("--question", default="My VPN keeps timing out", help="what each thread asks")
    return parser.parse_args(argv)


def call(url: str, *, key: str | None = None, body: dict | None = None) -> tuple[int, float, dict]:
    """One request: its status, its time in seconds and its JSON body (an error's too)."""
    headers = {"Content-Type": "application/json"} | ({"Authorization": f"Bearer {key}"} if key else {})
    request = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                     headers=headers, method="POST" if body is not None else "GET")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status, data = response.status, response.read()
    except urllib.error.HTTPError as err:
        status, data = err.code, err.read()
    return status, time.perf_counter() - started, json.loads(data or b"{}")


def percentile(times: list[float], share: float) -> float:
    return sorted(times)[min(len(times) - 1, int(share * len(times)))] if times else 0.0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    url = args.url.rstrip("/")
    status, _, stats = call(f"{url}/v1/stats", key=args.key)
    if status != 200:
        print(f"GET /v1/stats answered {status}: {stats.get('error', stats)}", file=sys.stderr)
        return 1
    per_minute = stats["requests_per_minute"]

    statuses: Counter[int] = Counter()
    answer_times: list[float] = []
    health_times: list[float] = []
    lock = threading.Lock()
    stop = time.monotonic() + args.seconds

    def ask() -> None:
        while time.monotonic() < stop:
            got, seconds, _ = call(f"{url}/v1/query", key=args.key, body={"question": args.question})
            with lock:
                statuses[got] += 1
                if got == 200:
                    answer_times.append(seconds)
            if got == 429:
                time.sleep(0.05)              # a real client would wait Retry-After: this one keeps pushing

    def check_health() -> None:
        while time.monotonic() < stop:
            got, seconds, _ = call(f"{url}/health/live")
            with lock:
                health_times.append(seconds if got == 200 else float("inf"))
            time.sleep(0.5)

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.clients + 1) as pool:
        pool.submit(check_health)
        for _ in range(args.clients):
            pool.submit(ask)
    took = time.monotonic() - started

    # One caller gets the burst (per_minute), then per_minute / 60 a second
    allowed = per_minute + int(per_minute / 60 * took)
    print(f"Load test: {args.clients} clients for {took:.1f} s, one key, a limit of {per_minute} a minute")
    print(f"  Requests: {sum(statuses.values())}; " + ", ".join(f"{count} x {code}"
                                                                 for code, count in sorted(statuses.items())))
    print(f"  Answered (200): median {statistics.median(answer_times) * 1000:.0f} ms, 95th percentile "
          f"{percentile(answer_times, 0.95) * 1000:.0f} ms" if answer_times else "  Answered (200): none")
    print(f"  /health/live while busy: {len(health_times)} checks, median {statistics.median(health_times) * 1000:.0f} "
          f"ms, slowest {max(health_times) * 1000:.0f} ms" if health_times else "  /health/live: not checked")
    held = statuses[200] <= allowed
    others = sorted(code for code in statuses if code not in (200, 429))
    print(f"  Rate limit: {statuses[200]} answered, at most {allowed} allowed in {took:.1f} s: "
          f"{'held' if held else 'NOT HELD'}" + (f"; unexpected statuses: {others}" if others else ""))
    return 0 if held and not others else 1


if __name__ == "__main__":
    sys.exit(main())
