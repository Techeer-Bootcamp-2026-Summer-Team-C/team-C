import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/api/client";
import { intervalFor, numberParam, updateParams, validEventDetailQuery } from "../src/lib/url";
import { canMutate, pollingInterval, retryDelay, shouldRetry } from "../src/query/policy";

describe("request lifecycle policy", () => {
  it("retries only 503 with 5s, 15s, 30s delays", () => {
    const unavailable = new ApiError({ status: 503, code: "SERVICE_UNAVAILABLE", message: "down", retryable: true, details: [], requestId: "req" });
    const forbidden = new ApiError({ status: 403, code: "FORBIDDEN", message: "no", retryable: false, details: [], requestId: "req" });
    expect([0, 1, 2, 3].map((count) => shouldRetry(count, unavailable))).toEqual([true, true, true, false]);
    expect(shouldRetry(0, forbidden)).toBe(false);
    expect([0, 1, 2, 3].map(retryDelay)).toEqual([5_000, 15_000, 30_000, 30_000]);
  });

  it("stops polling while the document is hidden", () => {
    const visibility = vi.spyOn(document, "visibilityState", "get");
    visibility.mockReturnValue("hidden");
    expect(pollingInterval(30_000)()).toBe(false);
    visibility.mockReturnValue("visible");
    expect(pollingInterval(30_000)()).toBe(30_000);
  });
});

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
});
