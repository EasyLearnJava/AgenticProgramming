/*
 * tests/unit/weather/wmo-codes.test.ts: the WMO code table.
 */
import { describe, expect, it } from "vitest";
import { toCondition } from "@/lib/weather/wmo-codes";

describe("toCondition", () => {
  it("gives WMO's words and an icon for a code", () => {
    expect(toCondition(0)).toEqual({ words: "Clear sky", icon: "☀️" });
    expect(toCondition(45).words).toBe("Fog");
    expect(toCondition(95).words).toBe("Thunderstorm");
  });

  it("says so for a code that isn't in the table, or a missing one", () => {
    expect(toCondition(4).words).toBe("Unknown conditions (WMO code 4)");
    expect(toCondition(null).words).toBe("Unknown conditions");
  });
});
