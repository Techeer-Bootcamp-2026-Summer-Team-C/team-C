import { CornerDownRight, GitFork, Terminal } from "lucide-react";
import type { CSSProperties } from "react";
import type { ProcessTreeNodeDto } from "../contracts";
import { useI18n } from "../i18n/LocaleContext";
import { formatDateTime } from "../lib/format";
import { EmptyState, StatusPill } from "./ui";

interface RenderedProcessNode {
  node: ProcessTreeNodeDto;
  depth: number;
}

export function ProcessTree({ nodes }: { nodes: readonly ProcessTreeNodeDto[] }) {
  const { t } = useI18n();
  const rendered = layoutProcessTree(nodes);
  if (!rendered.length) {
    return <EmptyState title={t("processTree.empty")} message={t("processTree.emptyDescription")} />;
  }
  return <div className="process-tree" role="tree" aria-label={t("processTree.aria")}>
    {rendered.map(({ node, depth }) => <article
      aria-current={node.selected ? "true" : undefined}
      className={node.selected ? "process-node selected" : "process-node"}
      key={node.pid}
      role="treeitem"
      style={{ "--tree-depth": depth } as CSSProperties}
    >
      <span className="process-branch" aria-hidden="true">{depth ? <CornerDownRight size={16} /> : <GitFork size={16} />}</span>
      <span className="process-icon"><Terminal aria-hidden="true" size={16} /></span>
      <span className="process-copy">
        <strong>{node.processName}</strong>
        <code>{node.commandLine ?? node.processPath ?? t("processTree.commandUnavailable")}</code>
        <small>{t("processTree.metadata", { time: formatDateTime(node.lastSeenAt), pid: node.pid, ppid: node.ppid ?? t("common.none"), count: node.eventCount })}</small>
      </span>
      <span className="process-flags">
        {node.selected ? <StatusPill label={t("processTree.selectedPid")} value="SELECTED PID" /> : null}
        {node.ppid !== null && !node.parentCaptured ? <StatusPill label={t("processTree.parentNotCaptured")} value="PARENT NOT CAPTURED" /> : null}
      </span>
    </article>)}
  </div>;
}

function layoutProcessTree(nodes: readonly ProcessTreeNodeDto[]): RenderedProcessNode[] {
  const byPid = new Map(nodes.map((node) => [node.pid, node]));
  const children = new Map<number, ProcessTreeNodeDto[]>();
  const roots: ProcessTreeNodeDto[] = [];
  for (const node of nodes) {
    if (node.ppid === null || node.ppid === node.pid || !byPid.has(node.ppid)) roots.push(node);
    else children.set(node.ppid, [...(children.get(node.ppid) ?? []), node]);
  }
  const chronological = (left: ProcessTreeNodeDto, right: ProcessTreeNodeDto) =>
    Date.parse(left.firstSeenAt) - Date.parse(right.firstSeenAt) || left.pid - right.pid;
  roots.sort(chronological);
  for (const siblings of children.values()) siblings.sort(chronological);
  const rendered: RenderedProcessNode[] = [];
  const visited = new Set<number>();
  const visit = (node: ProcessTreeNodeDto, depth: number) => {
    if (visited.has(node.pid)) return;
    visited.add(node.pid);
    rendered.push({ node, depth });
    for (const child of children.get(node.pid) ?? []) visit(child, Math.min(depth + 1, 12));
  };
  for (const root of roots) visit(root, 0);
  for (const node of [...nodes].sort(chronological)) visit(node, 0);
  return rendered;
}
