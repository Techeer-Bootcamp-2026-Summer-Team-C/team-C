import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest, buildQuery, configureApiAuth, configureApiRefresh } from "../src/api/client";

afterEach(() => {
  vi.unstubAllGlobals();
  configureApiAuth(null, null);
  configureApiRefresh(null);
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

  it("retries once with a fresh token after a single refresh on 401 INVALID_TOKEN", async () => {
    let refreshCalls = 0;
    configureApiRefresh(async () => {
      refreshCalls += 1;
      configureApiAuth("new-token", null);
      return true;
    });
    const unauthorizedBody = JSON.stringify({ error: { code: "INVALID_TOKEN", message: "Expired", retryable: false, details: [] }, meta: { requestId: "req_401" } });
    const okBody = JSON.stringify({ data: { total: 1 }, meta: { requestId: "req_retry" } });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(unauthorizedBody, { status: 401, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(okBody, { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const response = await apiRequest<{ total: number }>("/endpoints");
    expect(response.data.total).toBe(1);
    expect(refreshCalls).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const retryHeaders = new Headers(fetchMock.mock.calls[1]?.[1]?.headers as HeadersInit);
    expect(retryHeaders.get("Authorization")).toBe("Bearer new-token");
  });

  it("shares a single in-flight refresh across concurrent 401s", async () => {
    let refreshCalls = 0;
    configureApiRefresh(async () => {
      refreshCalls += 1;
      await Promise.resolve();
      configureApiAuth("new-token", null);
      return true;
    });
    const unauthorized = () => new Response(JSON.stringify({ error: { code: "INVALID_TOKEN", message: "Expired", retryable: false, details: [] }, meta: { requestId: "req_401" } }), { status: 401, headers: { "Content-Type": "application/json" } });
    const ok = () => new Response(JSON.stringify({ data: { total: 1 }, meta: { requestId: "req_ok" } }), { status: 200, headers: { "Content-Type": "application/json" } });
    const fetchMock = vi.fn().mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(ok()).mockResolvedValueOnce(ok());
    vi.stubGlobal("fetch", fetchMock);
    const [first, second] = await Promise.all([
      apiRequest<{ total: number }>("/endpoints"),
      apiRequest<{ total: number }>("/alerts"),
    ]);
    expect(first.data.total).toBe(1);
    expect(second.data.total).toBe(1);
    expect(refreshCalls).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("logs out once when the refresh attempt fails", async () => {
    const unauthorized = vi.fn();
    configureApiAuth("expired", unauthorized);
    configureApiRefresh(async () => false);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: "INVALID_TOKEN", message: "Expired", retryable: false, details: [] }, meta: { requestId: "req_401" } }), { status: 401, headers: { "Content-Type": "application/json" } })));
    await expect(apiRequest("/endpoints")).rejects.toBeInstanceOf(ApiError);
    expect(unauthorized).toHaveBeenCalledOnce();
  });

  it("does not attempt a refresh for the auth endpoints themselves", async () => {
    const refreshHandler = vi.fn(async () => true);
    configureApiRefresh(refreshHandler);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: "INVALID_REFRESH_TOKEN", message: "No session", retryable: false, details: [] }, meta: { requestId: "req_refresh" } }), { status: 401, headers: { "Content-Type": "application/json" } })));
    await expect(apiRequest("/auth/refresh", { method: "POST" })).rejects.toBeInstanceOf(ApiError);
    expect(refreshHandler).not.toHaveBeenCalled();
  });

  it("serializes repeated Archive endpointIds without empty values", () => {
    expect(buildQuery({ endpointIds: [1, 2], from: "a", empty: "", omitted: undefined })).toBe("?endpointIds=1&endpointIds=2&from=a");
  });
});
