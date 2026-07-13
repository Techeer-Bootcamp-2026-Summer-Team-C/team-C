import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest, buildQuery, configureApiAuth } from "../src/api/client";

afterEach(() => {
  vi.unstubAllGlobals();
  configureApiAuth(null, null);
});

describe("API envelope boundary", () => {
  it("returns the typed success envelope and sends the memory token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { total: 3 }, meta: { requestId: "req_ok" } }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    configureApiAuth("memory-token", null);
    const response = await apiRequest<{ total: number }>("/dashboard/summary");
    expect(response).toEqual({ data: { total: 3 }, meta: { requestId: "req_ok" } });
    const headers = new Headers(fetchMock.mock.calls[0]?.[1]?.headers as HeadersInit);
    expect(headers.get("Authorization")).toBe("Bearer memory-token");
  });

  it.each([403, 409, 503])("preserves the %s error envelope", async (status) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: status === 409 ? "ARCHIVE_NOT_READY" : `ERROR_${status}`, message: "Contract error", retryable: status === 503, details: [{ field: null, message: "State detail", context: { storageStatus: "ARCHIVED" } }] }, meta: { requestId: `req_${status}` } }), { status, headers: { "Content-Type": "application/json" } })));
    await expect(apiRequest("/events")).rejects.toMatchObject({ status, requestId: `req_${status}`, retryable: status === 503, details: [{ message: "State detail" }] });
  });

  it("clears authentication through the 401 callback", async () => {
    const unauthorized = vi.fn();
    configureApiAuth("expired", unauthorized);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: "INVALID_TOKEN", message: "Expired", retryable: false, details: [] }, meta: { requestId: "req_401" } }), { status: 401 })));
    await expect(apiRequest("/endpoints")).rejects.toBeInstanceOf(ApiError);
    expect(unauthorized).toHaveBeenCalledOnce();
  });

  it("serializes repeated Archive endpointIds without empty values", () => {
    expect(buildQuery({ endpointIds: [1, 2], from: "a", empty: "", omitted: undefined })).toBe("?endpointIds=1&endpointIds=2&from=a");
  });
});
