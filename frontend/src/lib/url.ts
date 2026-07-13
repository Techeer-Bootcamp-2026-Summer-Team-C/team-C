import type { DashboardInterval, TimePreset } from "../contracts";

export function stringParam(params: URLSearchParams, key: string, fallback = ""): string {
  return params.get(key) ?? fallback;
}

export function numberParam(params: URLSearchParams, key: string, fallback: number): number {
  const value = Number(params.get(key));
  return Number.isInteger(value) && value > 0 ? value : fallback;
}

export function updateParams(
  current: URLSearchParams,
  values: Record<string, string | number | null | undefined>,
  resetPage = true,
): URLSearchParams {
  const next = new URLSearchParams(current);
  for (const [key, value] of Object.entries(values)) {
    if (value === undefined || value === null || value === "") next.delete(key);
    else next.set(key, String(value));
  }
  if (resetPage) next.delete("page");
  return next;
}

export function timePreset(params: URLSearchParams): TimePreset {
  const value = params.get("timePreset");
  return value === "LATEST_15M" || value === "LATEST_1H" || value === "LATEST_7D" || value === "CUSTOM"
    ? value
    : "LATEST_24H";
}

export function intervalFor(preset: TimePreset, from?: string, to?: string): DashboardInterval {
  if (preset === "LATEST_15M") return "1m";
  if (preset === "LATEST_1H") return "5m";
  if (preset === "LATEST_24H") return "1h";
  if (preset === "LATEST_7D") return "1d";
  if (!from || !to) return "1h";
  const hours = (Date.parse(to) - Date.parse(from)) / 3_600_000;
  if (hours <= 6) return "5m";
  return hours <= 48 ? "1h" : "1d";
}

export function validEventDetailQuery(params: URLSearchParams): boolean {
  const endpointId = Number(params.get("endpointId"));
  const occurredAt = params.get("occurredAt");
  return Number.isInteger(endpointId) && endpointId > 0 && occurredAt !== null && !Number.isNaN(Date.parse(occurredAt));
}

export function localDateTimeValue(timestamp: string): string {
  const date = new Date(timestamp);
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return shifted.toISOString().slice(0, 16);
}

export function utcFromLocal(value: string): string {
  return new Date(value).toISOString();
}
