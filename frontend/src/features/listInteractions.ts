export interface FilterDefinition {
  key: string;
  label: string;
  format?: (value: string) => string;
}

export interface AppliedFilterDescriptor {
  key: string;
  label: string;
  value: string;
}

export function appliedFilterDescriptors(params: URLSearchParams, definitions: readonly FilterDefinition[]): AppliedFilterDescriptor[] {
  return definitions.flatMap((definition) => {
    const value = params.get(definition.key);
    if (!value) return [];
    return [{ key: definition.key, label: definition.label, value: definition.format ? definition.format(value) : value }];
  });
}

export function removeListFilter(params: URLSearchParams, key: string): URLSearchParams {
  const next = new URLSearchParams(params);
  next.delete(key);
  if (key === "timePreset") {
    next.delete("from");
    next.delete("to");
  }
  next.delete("page");
  return next;
}

export function hasInvalidEnum(params: URLSearchParams, key: string, allowed: readonly string[]): boolean {
  const value = params.get(key);
  return value !== null && !allowed.includes(value);
}

export function hasInvalidPositiveInteger(params: URLSearchParams, key: string): boolean {
  const value = params.get(key);
  if (value === null) return false;
  const parsed = Number(value);
  return !Number.isInteger(parsed) || parsed <= 0;
}

export function hasInvalidPagination(params: URLSearchParams): boolean {
  if (hasInvalidPositiveInteger(params, "page")) return true;
  const size = params.get("size");
  if (size === null) return false;
  const parsed = Number(size);
  return !Number.isInteger(parsed) || parsed < 1 || parsed > 200;
}

export function hasInvalidText(params: URLSearchParams, key: string, maximum: number): boolean {
  const value = params.get(key);
  return value !== null && (value.trim().length < 1 || value.trim().length > maximum);
}

export function selectedSearch(params: URLSearchParams, value: string | number): string {
  const next = new URLSearchParams(params);
  next.set("selected", String(value));
  return next.size ? `?${next}` : "";
}

export function isSelected(params: URLSearchParams, value: string | number): boolean {
  return params.get("selected") === String(value);
}

export function eventDetailSearch(params: URLSearchParams, event: { eventId: string; endpointId: number; occurredAt: string }): string {
  const returnParams = new URLSearchParams(params);
  returnParams.set("selected", event.eventId);
  const returnTo = `/events${returnParams.size ? `?${returnParams}` : ""}`;
  const detailParams = new URLSearchParams({ endpointId: String(event.endpointId), occurredAt: event.occurredAt, returnTo });
  return `?${detailParams}`;
}

export function safeReturnPath(params: URLSearchParams, fallback: string): string {
  const value = params.get("returnTo");
  return value && value.startsWith("/events") && !value.startsWith("//") ? value : fallback;
}
