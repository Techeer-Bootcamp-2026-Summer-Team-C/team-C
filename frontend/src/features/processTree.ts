import type { EventDto } from "../contracts";

export interface ProcessTreeNode {
  event: EventDto;
  depth: number;
  orphaned: boolean;
  selected: boolean;
}

export function processTreeWindow(occurredAt: string): { from: string; to: string } {
  const pivot = Date.parse(occurredAt);
  return {
    from: new Date(pivot - 30 * 60_000).toISOString(),
    to: new Date(pivot + 5 * 60_000).toISOString(),
  };
}

export function buildProcessTree(events: readonly EventDto[], selectedPid: number | null): ProcessTreeNode[] {
  const byPid = new Map<number, EventDto>();
  for (const event of events) {
    if (event.eventType !== "PROCESS_EXECUTION" || event.pid === null) continue;
    const existing = byPid.get(event.pid);
    if (!existing || Date.parse(event.occurredAt) >= Date.parse(existing.occurredAt)) byPid.set(event.pid, event);
  }

  const children = new Map<number, EventDto[]>();
  const roots: EventDto[] = [];
  for (const event of byPid.values()) {
    if (event.ppid === null || event.ppid === event.pid || !byPid.has(event.ppid)) {
      roots.push(event);
      continue;
    }
    const siblings = children.get(event.ppid) ?? [];
    siblings.push(event);
    children.set(event.ppid, siblings);
  }

  const chronological = (left: EventDto, right: EventDto) =>
    Date.parse(left.occurredAt) - Date.parse(right.occurredAt) || (left.pid ?? 0) - (right.pid ?? 0);
  roots.sort(chronological);
  for (const siblings of children.values()) siblings.sort(chronological);

  const nodes: ProcessTreeNode[] = [];
  const visited = new Set<number>();
  function visit(event: EventDto, depth: number): void {
    if (event.pid === null || visited.has(event.pid)) return;
    visited.add(event.pid);
    nodes.push({
      event,
      depth,
      orphaned: event.ppid !== null && event.ppid !== event.pid && !byPid.has(event.ppid),
      selected: selectedPid !== null && event.pid === selectedPid,
    });
    for (const child of children.get(event.pid) ?? []) visit(child, Math.min(depth + 1, 12));
  }
  for (const root of roots) visit(root, 0);
  for (const event of [...byPid.values()].sort(chronological)) visit(event, 0);
  return nodes;
}
