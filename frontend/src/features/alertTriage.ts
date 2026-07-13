import type { AlertDto } from "../contracts";

export function nextActionableAlert(items: readonly AlertDto[], currentAlertId: number): AlertDto | null {
  const actionable = items.filter((item) => item.status !== "RESOLVED" && item.alertId !== currentAlertId);
  if (!actionable.length) return null;
  const currentIndex = items.findIndex((item) => item.alertId === currentAlertId);
  if (currentIndex < 0) return actionable[0] ?? null;
  return items.slice(currentIndex + 1).find((item) => item.status !== "RESOLVED") ?? actionable[0] ?? null;
}

export function alertDetailUrl(alertId: number, params: URLSearchParams): string {
  return `/alerts/${alertId}${params.size ? `?${params.toString()}` : ""}`;
}
