import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { api } from "../api/endpoints";
import { ProcessTree } from "../components/ProcessTree";
import { RawPayloadViewer } from "../components/RawPayloadViewer";
import { DefinitionGrid, EmptyState, ErrorState, PageHeader, Panel, Skeleton, StatusPill } from "../components/ui";
import type { EventDetailDto } from "../contracts";
import { eventDetailGroups, type EventDetailGroup } from "../features/eventPresentation";
import { safeReturnPath } from "../features/listInteractions";
import { processTreeWindow } from "../features/processTree";
import { useI18n } from "../i18n/LocaleContext";
import { displayNullable, formatDateTime } from "../lib/format";
import { validEventDetailQuery } from "../lib/url";

export function EventDetailPage() {
  const { t } = useI18n();
  const eventId = useParams().eventId ?? "";
  const [params] = useSearchParams();
  const valid = Boolean(eventId) && validEventDetailQuery(params);
  const endpointId = Number(params.get("endpointId"));
  const occurredAt = params.get("occurredAt") ?? "";
  const returnPath = safeReturnPath(params, "/events");
  const result = useQuery({ queryKey: ["event", eventId, endpointId, occurredAt], queryFn: ({ signal }) => api.event(eventId, { endpointId, occurredAt }, signal), enabled: valid });
  const event = result.data?.data;
  const treeWindow = event ? processTreeWindow(event.occurredAt) : null;
  const treeResult = useQuery({
    queryKey: ["process-tree", event?.endpointId, treeWindow?.from, treeWindow?.to],
    queryFn: ({ signal }) => api.processTree(event!.endpointId, {
      timePreset: "CUSTOM",
      from: treeWindow!.from,
      to: treeWindow!.to,
      ...(event!.pid !== null ? { selectedPid: event!.pid } : {}),
    }, signal),
    enabled: Boolean(event && treeWindow),
  });
  const archiveNotReady = result.error instanceof ApiError && result.error.code === "ARCHIVE_NOT_READY";
  if (!valid) return <div className="page-stack"><Link className="back-link" to={returnPath}><ArrowLeft aria-hidden="true" size={15} />{t("events.stream")}</Link><EmptyState title={t("event.routingMissing")} message={t("event.routingDescription")} /><Link className="button" to={returnPath}>{t("event.return")}</Link></div>;
  return <div className="page-stack">
    <Link className="back-link" to={returnPath}><ArrowLeft aria-hidden="true" size={15} />{t("events.stream")}</Link>
    {result.isPending ? <Skeleton rows={12} /> : null}
    {result.error ? <ErrorState archiveAction={archiveNotReady} error={result.error} {...(!archiveNotReady ? { onRetry: () => void result.refetch() } : {})} /> : null}
    {event ? <EventDetail event={event} processTree={treeResult.isPending ? <Skeleton rows={5} />
      : treeResult.error ? <ErrorState error={treeResult.error} onRetry={() => void treeResult.refetch()} />
        : treeResult.data ? <ProcessTree nodes={treeResult.data.data.nodes} /> : null} /> : null}
  </div>;
}

function EventDetail({ event, processTree }: { event: EventDetailDto; processTree: ReactNode }) {
  const { locale, t } = useI18n();
  return <>
    <PageHeader eyebrow={`EVENT · SCHEMA V${event.schemaVersion}`} title={event.processName ?? event.remoteDomain ?? event.filePath ?? event.eventType} description={event.eventId} actions={<StatusPill value={event.eventType} />} />
    <section className="detail-grid event-detail-grid">
      {eventDetailGroups(event).map((group) => <Panel key={group} title={t(groupTitle(group))} subtitle={t(groupSubtitle(group))}><DefinitionGrid items={groupItems(event, group, locale, t)} /></Panel>)}
      <Panel title={t("event.payloadIdentity")} subtitle={t("event.payloadSubtitle")}><DefinitionGrid items={[{ label: t("event.payloadSha"), value: <code>{event.payloadSha256}</code> }, { label: t("event.schemaVersion"), value: event.schemaVersion }]} /></Panel>
      <Panel className="wide" title={t("event.processTree")} subtitle={t("event.processTreeSubtitle")} meta={<StatusPill value="READ ONLY" />}>{processTree}</Panel>
      <div className="wide"><RawPayloadViewer payload={event.rawPayload} /></div>
    </section>
  </>;
}

function groupItems(event: EventDetailDto, group: EventDetailGroup, locale: "EN" | "KO", t: ReturnType<typeof useI18n>["t"]): { label: string; value: ReactNode }[] {
  switch (group) {
    case "IDENTITY": return [
      { label: "Event ID", value: <code>{event.eventId}</code> }, { label: t("event.batchId"), value: <code>{event.batchId}</code> },
      { label: "Endpoint", value: <Link to={`/endpoints/${event.endpointId}`}>{event.hostname} · {event.endpointId}</Link> }, { label: "Agent ID", value: <code>{event.agentId}</code> },
      { label: t("endpoints.operatingSystem"), value: event.osType }, { label: t("endpoint.ipAddress"), value: displayNullable(event.ipAddress) },
      { label: t("event.occurred"), value: formatDateTime(event.occurredAt) }, { label: t("event.ingested"), value: formatDateTime(event.ingestedAt) },
    ];
    case "PROCESS": return [
      { label: t("event.processName"), value: displayNullable(event.processName) }, { label: t("event.processPath"), value: displayNullable(event.processPath) },
      { label: "PID", value: event.pid ?? t("common.notAvailable") }, { label: "PPID", value: event.ppid ?? t("common.notAvailable") },
      { label: t("event.commandLine"), value: displayNullable(event.commandLine) }, { label: t("event.user"), value: displayNullable(event.userName) },
    ];
    case "FILE": return [
      { label: t("event.filePath"), value: displayNullable(event.filePath) }, { label: t("event.fileAction"), value: displayNullable(event.fileAction) }, { label: "File SHA-256", value: displayNullable(event.fileHashSha256) },
    ];
    case "NETWORK": return [
      { label: "Remote IP", value: displayNullable(event.remoteIp) }, { label: locale === "KO" ? "Remote Domain" : "Remote domain", value: displayNullable(event.remoteDomain) },
      { label: locale === "KO" ? "Remote Port" : "Remote port", value: event.remotePort ?? t("common.notAvailable") }, { label: "Protocol", value: displayNullable(event.protocol) },
    ];
    case "DNS": return [
      { label: "DNS query", value: displayNullable(event.dnsQuery) }, { label: "DNS record type", value: displayNullable(event.dnsRecordType) },
      { label: "DNS response", value: displayNullable(event.dnsResponseCode) }, { label: t("event.dnsAnswers"), value: event.dnsAnswers.length ? event.dnsAnswers.join(", ") : t("common.none") },
    ];
    case "HTTP_TLS": return [
      { label: "L7 protocol", value: displayNullable(event.l7Protocol) }, { label: "HTTP method", value: displayNullable(event.httpMethod) }, { label: "HTTP host", value: displayNullable(event.httpHost) },
      { label: "URL", value: displayNullable(event.url) }, { label: "HTTP status", value: event.httpStatusCode ?? t("common.notAvailable") }, { label: "HTTP user agent", value: displayNullable(event.httpUserAgent) },
      { label: "TLS SNI", value: displayNullable(event.tlsSni) }, { label: "TLS version", value: displayNullable(event.tlsVersion) }, { label: "TLS subject", value: displayNullable(event.tlsCertificateSubject) },
      { label: "TLS issuer", value: displayNullable(event.tlsCertificateIssuer) }, { label: "TLS SHA-256", value: displayNullable(event.tlsCertificateSha256) },
    ];
  }
}

function groupTitle(group: EventDetailGroup) {
  return { IDENTITY: "event.groupIdentity", PROCESS: "event.groupProcess", FILE: "event.groupFile", NETWORK: "event.groupNetwork", DNS: "event.groupDns", HTTP_TLS: "event.groupHttpTls" }[group] as "event.groupIdentity";
}

function groupSubtitle(group: EventDetailGroup) {
  return { IDENTITY: "event.groupIdentitySubtitle", PROCESS: "event.groupProcessSubtitle", FILE: "event.groupFileSubtitle", NETWORK: "event.groupNetworkSubtitle", DNS: "event.groupDnsSubtitle", HTTP_TLS: "event.groupHttpTlsSubtitle" }[group] as "event.groupIdentitySubtitle";
}
