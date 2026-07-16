import type { AlertDto, AlertListQuery } from "../contracts";
import { readTimeFilter } from "../components/filters";
import { allowedValue, positiveInteger } from "../lib/params";

export function nextActionableAlert(items: readonly AlertDto[], currentAlertId: number): AlertDto | null {
  const actionable = items.filter((item) => item.status !== "RESOLVED" && item.alertId !== currentAlertId);
  if (!actionable.length) return null;
  const currentIndex = items.findIndex((item) => item.alertId === currentAlertId);
  if (currentIndex < 0) return actionable[0] ?? null;
  return items.slice(currentIndex + 1).find((item) => item.status !== "RESOLVED") ?? actionable[0] ?? null;
}

export function alertDetailUrl(alertId: number, params: URLSearchParams): string {
  const next = new URLSearchParams(params);
  next.set("selected", String(alertId));
  return `/alerts/${alertId}?${next.toString()}`;
}

export function alertTriageQueueQuery(params: URLSearchParams): AlertListQuery {
  const time = readTimeFilter(params);
  const query: AlertListQuery = {
    ...time.query,
    page: 1,
    size: 500,
    sortBy: allowedValue(params.get("sortBy"), ["priority", "detectedAt", "severity", "riskScore", "status"] as const) ?? "priority",
    sortOrder: allowedValue(params.get("sortOrder"), ["asc", "desc"] as const) ?? "desc",
  };
  const status = allowedValue(params.get("status"), ["OPEN", "IN_PROGRESS", "RESOLVED"] as const);
  const severity = allowedValue(params.get("severity"), ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const);
  const endpointId = positiveInteger(params.get("endpointId"));
  const ruleCode = (params.get("ruleCode") ?? "").trim();
  if (status) query.status = status;
  if (severity) query.severity = severity;
  if (endpointId) query.endpointId = endpointId;
  if (ruleCode) query.ruleCode = ruleCode;
  return query;
}
