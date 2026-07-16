import { describe, expect, it } from "vitest";
import type { AlertDto } from "../src/contracts";
import { alertDetailUrl, alertTriageQueueQuery, nextActionableAlert } from "../src/features/alertTriage";

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
    expect(alertDetailUrl(42, new URLSearchParams("severity=CRITICAL&sortOrder=asc&selected=7"))).toBe(
      "/alerts/42?severity=CRITICAL&sortOrder=asc&selected=42",
    );
  });

  it("preserves the complete list scope and user ordering in the active queue query", () => {
    expect(alertTriageQueueQuery(new URLSearchParams("timePreset=LATEST_7D&status=IN_PROGRESS&severity=HIGH&endpointId=1001&ruleCode=PROC-001&sortBy=riskScore&sortOrder=asc&page=4"))).toEqual({
      timePreset: "LATEST_7D",
      status: "IN_PROGRESS",
      severity: "HIGH",
      endpointId: 1001,
      ruleCode: "PROC-001",
      sortBy: "riskScore",
      sortOrder: "asc",
      page: 1,
      size: 500,
    });
  });
});
