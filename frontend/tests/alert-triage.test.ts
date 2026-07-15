import { describe, expect, it } from "vitest";
import type { AlertDto } from "../src/contracts";
import { alertDetailUrl, nextActionableAlert } from "../src/features/alertTriage";

function alert(alertId: number, status: AlertDto["status"]): AlertDto {
  return { alertId, status } as AlertDto;
}

describe("alert triage navigation", () => {
  it("selects the next unresolved alert and skips resolved rows", () => {
    expect(nextActionableAlert([alert(1, "OPEN"), alert(2, "RESOLVED"), alert(3, "IN_PROGRESS")], 1)?.alertId).toBe(3);
  });

  it("wraps to the first actionable alert at the end of the queue", () => {
    expect(nextActionableAlert([alert(1, "OPEN"), alert(2, "IN_PROGRESS")], 2)?.alertId).toBe(1);
  });

  it("preserves queue filters in detail navigation", () => {
    expect(alertDetailUrl(42, new URLSearchParams("severity=CRITICAL&sortOrder=asc"))).toBe(
      "/alerts/42?severity=CRITICAL&sortOrder=asc",
    );
  });
});
