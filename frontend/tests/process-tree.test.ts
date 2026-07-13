import { describe, expect, it } from "vitest";
import type { EventDto } from "../src/contracts";
import { buildProcessTree, processTreeWindow } from "../src/features/processTree";

function process(pid: number, ppid: number | null, occurredAt: string): EventDto {
  return {
    eventId: `event-${pid}`, batchId: "batch", endpointId: 1, agentId: "agent", hostname: "HOST",
    osType: "WINDOWS", ipAddress: null, eventType: "PROCESS_EXECUTION", occurredAt, ingestedAt: occurredAt,
    processName: `proc-${pid}`, processPath: null, pid, ppid, commandLine: null, userName: null,
    filePath: null, fileAction: null, fileHashSha256: null, remoteIp: null, remoteDomain: null,
    remotePort: null, protocol: null, dnsQuery: null, dnsRecordType: null, dnsResponseCode: null,
    dnsAnswers: [], l7Protocol: null, httpMethod: null, httpHost: null, url: null, httpStatusCode: null,
    httpUserAgent: null, tlsSni: null, tlsVersion: null, tlsCertificateSubject: null,
    tlsCertificateIssuer: null, tlsCertificateSha256: null,
  };
}

describe("read-only process tree", () => {
  it("orders parent and child nodes and marks the selected PID", () => {
    const nodes = buildProcessTree([
      process(30, 20, "2026-07-13T00:02:00Z"),
      process(10, null, "2026-07-13T00:00:00Z"),
      process(20, 10, "2026-07-13T00:01:00Z"),
    ], 20);
    expect(nodes.map((node) => [node.event.pid, node.depth, node.selected])).toEqual([
      [10, 0, false], [20, 1, true], [30, 2, false],
    ]);
  });

  it("keeps an event with an uncaptured parent as an orphan root", () => {
    const [node] = buildProcessTree([process(30, 999, "2026-07-13T00:02:00Z")], null);
    expect(node).toMatchObject({ depth: 0, orphaned: true });
  });

  it("uses a bounded 30-minute lookback and five-minute lookahead", () => {
    expect(processTreeWindow("2026-07-13T01:00:00Z")).toEqual({
      from: "2026-07-13T00:30:00.000Z", to: "2026-07-13T01:05:00.000Z",
    });
  });
});
