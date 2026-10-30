/*
 * tests/unit/utils.test.ts: every helper in lib/utils.ts.
 */
import { describe, expect, it } from "vitest";
import {
  addDays,
  celsiusToFahrenheit,
  formatDuration,
  formatLocalTime,
  newRequestId,
  once,
  roundCoordinate,
  timeoutSignal,
  toAbortKind,
  toHost,
  toLocalDateTime,
  toRef,
  toRequestId,
  toRetryAfterMs,
  toWeekday,
  toWireText,
  withRetry,
} from "@/lib/utils";

describe("toWireText", () => {
  it("writes a request without a body as its request line and headers", () => {
    expect(toWireText({ method: "GET", url: "https://example.com/a?b=1", headers: {} })).toBe(
      "GET https://example.com/a?b=1",
    );
  });

  it("writes headers one per line, then a blank line and the body", () => {
    const text = toWireText({
      method: "POST",
      url: "https://example.com/run",
      headers: { Authorization: "Bearer <TOKEN>", "Content-Type": "application/json" },
      body: '{"a":1}',
    });
    expect(text).toBe(
      'POST https://example.com/run\nAuthorization: Bearer <TOKEN>\nContent-Type: application/json\n\n{"a":1}',
    );
  });
});

describe("toHost", () => {
  it("takes the host from a URL, with or without a path or query", () => {
    expect(toHost("https://api.apify.com/v2/acts/x/run-sync-get-dataset-items?timeout=18")).toBe("api.apify.com");
    expect(toHost("https://mcp.apify.com/?tools=gochujang/open-meteo-weather-forecast")).toBe("mcp.apify.com");
    expect(toHost("https://geocoding-api.open-meteo.com")).toBe("geocoding-api.open-meteo.com");
  });

  it("keeps a placeholder host as it's written", () => {
    expect(toHost("https://<this deployment>/api/mcp")).toBe("<this deployment>");
  });
});

describe("roundCoordinate", () => {
  it("rounds to 2 decimals unless told otherwise", () => {
    expect(roundCoordinate(48.85341)).toBe(48.85);
    expect(roundCoordinate(2.3488)).toBe(2.35);
    expect(roundCoordinate(-96.80359)).toBe(-96.8);
    expect(roundCoordinate(48.85341, 1)).toBe(48.9);
  });
});

describe("formatDuration", () => {
  it("writes milliseconds as seconds with one decimal, and anything under 50 ms as <0.1 s", () => {
    expect(formatDuration(587)).toBe("0.6 s");
    expect(formatDuration(12_340)).toBe("12.3 s");
    expect(formatDuration(4)).toBe("<0.1 s");
  });
});

describe("formatLocalTime", () => {
  it("gives a moment's clock time in the place's time zone, not the machine's", () => {
    expect(formatLocalTime("2026-10-29T19:07:00Z", "Europe/Paris")).toBe("20:07");
    expect(formatLocalTime("2026-10-29T19:07:00Z", "America/Chicago")).toBe("14:07");
    expect(formatLocalTime("2026-10-29T19:07:00Z", "Asia/Kolkata")).toBe("00:37");
  });
});

describe("toWeekday", () => {
  it("names the weekday of a calendar date, whatever the machine's time zone", () => {
    expect(toWeekday("2026-10-29")).toBe("Thursday");
    expect(toWeekday("2026-10-30")).toBe("Friday");
    expect(toWeekday("2026-11-01")).toBe("Sunday");
  });
});

describe("timeoutSignal", () => {
  it("fires after its time", async () => {
    const signal = timeoutSignal(10);
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(signal.aborted).toBe(true);
    expect((signal.reason as Error).name).toBe("TimeoutError");
  });

  it("fires at once when its parent does", () => {
    const parent = new AbortController();
    const signal = timeoutSignal(60_000, parent.signal);
    parent.abort();
    expect(signal.aborted).toBe(true);
    expect((signal.reason as Error).name).toBe("AbortError");
  });
});

describe("toRetryAfterMs", () => {
  it("reads a number of seconds, and nothing else", () => {
    expect(toRetryAfterMs("2")).toBe(2000);
    expect(toRetryAfterMs(" 0 ")).toBe(0);
    expect(toRetryAfterMs(null)).toBeUndefined();
    expect(toRetryAfterMs("Thu, 29 Oct 2026 19:00:00 GMT")).toBeUndefined();
  });
});

describe("withRetry", () => {
  const always = { shouldRetry: () => true, waitMs: () => 0 };

  it("returns the first success", async () => {
    let calls = 0;
    const result = await withRetry(
      async () => {
        calls += 1;
        if (calls === 1) {
          throw new Error("first try fails");
        }
        return "ok";
      },
      { tries: 2, ...always },
    );
    expect([result, calls]).toEqual(["ok", 2]);
  });

  it("stops after the last try, or when shouldRetry says no, with the last error", async () => {
    let calls = 0;
    const failing = async (): Promise<never> => {
      calls += 1;
      throw new Error(`try ${calls}`);
    };
    await expect(withRetry(failing, { tries: 3, ...always })).rejects.toThrow("try 3");
    calls = 0;
    await expect(withRetry(failing, { tries: 3, shouldRetry: () => false, waitMs: () => 0 })).rejects.toThrow("try 1");
  });

  it("stops waiting, with the signal's reason, when its signal fires during the wait", async () => {
    const controller = new AbortController();
    const started = Date.now();
    const pending = withRetry(
      async () => {
        throw new Error("fails");
      },
      { tries: 2, shouldRetry: () => true, waitMs: () => 60_000, signal: controller.signal },
    );
    setTimeout(() => controller.abort(), 20);
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(Date.now() - started).toBeLessThan(5000);
  });

  it("stops with the signal's reason when the signal fired while the task ran", async () => {
    const controller = new AbortController();
    const pending = withRetry(
      async () => {
        controller.abort();
        throw new Error("fails");
      },
      { tries: 2, ...always, signal: controller.signal },
    );
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("once", () => {
  it("runs the function the first time only, and gives every call the first call's result", () => {
    let runs = 0;
    const closeOnce = once(() => {
      runs += 1;
      return `closed ${runs}`;
    });
    expect([closeOnce(), closeOnce(), closeOnce()]).toEqual(["closed 1", "closed 1", "closed 1"]);
    expect(runs).toBe(1);
  });
});

describe("toAbortKind", () => {
  it("tells a time limit from a stop, whatever the stop's error is called", () => {
    expect(toAbortKind(undefined)).toBe("none");
    expect(toAbortKind(new AbortController().signal)).toBe("none");
    const timedOut = new AbortController();
    timedOut.abort(new DOMException("The operation timed out.", "TimeoutError"));
    expect(toAbortKind(timedOut.signal)).toBe("timeout");
    const stopped = new AbortController();
    stopped.abort();
    expect(toAbortKind(stopped.signal)).toBe("stop");
    const closed = new AbortController();
    closed.abort(Object.assign(new Error("The browser closed the connection."), { name: "ResponseAborted" }));
    expect(toAbortKind(closed.signal)).toBe("stop");
  });
});

describe("request ids", () => {
  it("makes a new id of 16 hex characters, a different one each time", () => {
    expect(newRequestId()).toMatch(/^[0-9a-f]{16}$/);
    expect(newRequestId()).not.toBe(newRequestId());
  });

  it("takes the first header value that looks like a request id, and makes one when none does", () => {
    const vercelId = "iad1::iad1::abcde-1730211234567-f3c2b1a0d9e8";
    expect(toRequestId(vercelId)).toBe(vercelId);
    expect(toRequestId(null, vercelId)).toBe(vercelId);
    expect(toRequestId("chat-7f3a", vercelId)).toBe("chat-7f3a");
    expect(toRequestId("not an id\nevent=forged")).toMatch(/^[0-9a-f]{16}$/);
    expect(toRequestId("x".repeat(129))).toMatch(/^[0-9a-f]{16}$/);
    expect(toRequestId(null)).toMatch(/^[0-9a-f]{16}$/);
  });

  it("shows a request id as its ref, its last 8 letters and digits", () => {
    expect(toRef("iad1::iad1::abcde-1730211234567-f3c2b1a0d9e8")).toBe("b1a0d9e8");
    expect(toRef("7f3a9c01aa55bb66")).toBe("aa55bb66");
  });
});

describe("celsiusToFahrenheit", () => {
  it("converts to a tenth of a degree, as Open-Meteo gives temperatures", () => {
    expect(celsiusToFahrenheit(0)).toBe(32);
    expect(celsiusToFahrenheit(11.9)).toBe(53.4);
    expect(celsiusToFahrenheit(15.6)).toBe(60.1);
    expect(celsiusToFahrenheit(-40)).toBe(-40);
  });
});

describe("toLocalDateTime", () => {
  it("gives a moment's date and time in a time zone: an evening in Dallas is already the next day in UTC", () => {
    expect(toLocalDateTime("2026-10-30T03:00:00Z", "America/Chicago")).toBe("2026-10-29T22:00");
    expect(toLocalDateTime("2026-10-30T03:00:00Z", "Europe/Paris")).toBe("2026-10-30T04:00");
    expect(toLocalDateTime("2026-10-30T03:00:00Z", "Asia/Tokyo")).toBe("2026-10-30T12:00");
    expect(toLocalDateTime("2026-10-30T00:00:00Z", "UTC")).toBe("2026-10-30T00:00");
  });

  it("follows daylight saving time: 1:30 comes twice in Chicago on 1 November 2026", () => {
    expect(toLocalDateTime("2026-11-01T06:30:00Z", "America/Chicago")).toBe("2026-11-01T01:30");
    expect(toLocalDateTime("2026-11-01T07:30:00Z", "America/Chicago")).toBe("2026-11-01T01:30");
  });
});

describe("addDays", () => {
  it("counts calendar days, across months and years", () => {
    expect(addDays("2026-10-29", 1)).toBe("2026-10-30");
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  });
});
