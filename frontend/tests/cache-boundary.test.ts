import { expect, it, vi } from "vitest";
import { invalidateAlertData } from "../src/pages/AlertDetailPage";
import { invalidateIncidentData } from "../src/pages/IncidentDetailPage";

it("invalidates Alert detail, Alert lists, and Endpoint Risk views after mutation", async () => {
  const invalidateQueries = vi.fn().mockResolvedValue(undefined);
  await invalidateAlertData({ invalidateQueries } as never, 42);
  expect(invalidateQueries.mock.calls.map((call) => call[0].queryKey)).toEqual([["alert", 42], ["alerts"], ["alert-triage-queue"], ["endpoints"]]);
});

it("invalidates Incident detail, queues, Endpoint Risk, and Dashboard views after mutation", async () => {
  const invalidateQueries = vi.fn().mockResolvedValue(undefined);
  await invalidateIncidentData({ invalidateQueries } as never, 21);
  expect(invalidateQueries.mock.calls.map((call) => call[0].queryKey)).toEqual([
    ["incident", 21],
    ["incidents"],
    ["incident-workbench-queue"],
    ["endpoints"],
    ["dashboard"],
  ]);
});
