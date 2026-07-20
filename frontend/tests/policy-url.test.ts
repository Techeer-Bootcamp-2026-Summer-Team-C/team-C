import { describe, expect, it } from "vitest";
import { intervalFor, navigationDestination, navigationTimeScope, numberParam, updateParams, validEventDetailQuery } from "../src/lib/url";
import { canMutate } from "../src/query/policy";

describe("URL and role contracts", () => {
  it("restores pagination and resets page when a filter changes", () => {
    const params = new URLSearchParams("status=OPEN&page=4&size=50");
    expect(numberParam(params, "page", 1)).toBe(4);
    expect(updateParams(params, { severity: "HIGH" }).toString()).toBe("status=OPEN&size=50&severity=HIGH");
  });

  it("requires Event endpointId and occurredAt query", () => {
    expect(validEventDetailQuery(new URLSearchParams("endpointId=1&occurredAt=2026-07-12T00%3A00%3A00Z"))).toBe(true);
    expect(validEventDetailQuery(new URLSearchParams("endpointId=1"))).toBe(false);
  });

  it("keeps Archive and Alert mutations away from VIEWER", () => {
    expect(canMutate("ADMIN")).toBe(true);
    expect(canMutate("ANALYST")).toBe(true);
    expect(canMutate("VIEWER")).toBe(false);
  });

  it("selects Dashboard interval without constructing chart buckets", () => {
    expect(intervalFor("LATEST_15M")).toBe("1m");
    expect(intervalFor("LATEST_24H")).toBe("1h");
    expect(intervalFor("CUSTOM", "2026-07-12T00:00:00Z", "2026-07-12T04:00:00Z")).toBe("5m");
  });

  it("copies only valid time scope to time-aware navigation routes", () => {
    const custom = navigationTimeScope("timePreset=CUSTOM&from=2026-07-12T00%3A00%3A00Z&to=2026-07-13T00%3A00%3A00Z&status=OPEN");
    expect(custom).toBe("timePreset=CUSTOM&from=2026-07-12T00%3A00%3A00Z&to=2026-07-13T00%3A00%3A00Z");
    expect(navigationDestination("/incidents", custom!)).toContain("/incidents?timePreset=CUSTOM");
    expect(navigationDestination("/operations/archives", custom!)).toBe("/operations/archives");
    expect(navigationTimeScope("timePreset=CUSTOM&from=2026-07-13T00%3A00%3A00Z&to=2026-07-12T00%3A00%3A00Z")).toBeNull();
  });
});
