import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { api } from "../api/endpoints";
import { DefinitionGrid, EmptyState, ErrorState, PageHeader, Panel, Skeleton, StatusPill } from "../components/ui";
import { displayNullable, formatDateTime } from "../lib/format";
import { useI18n } from "../i18n/LocaleContext";
import { validEventDetailQuery } from "../lib/url";

export function EventDetailPage() {
  const { t } = useI18n();
  const eventId = useParams().eventId ?? "";
  const [params] = useSearchParams();
  const valid = Boolean(eventId) && validEventDetailQuery(params);
  const endpointId = Number(params.get("endpointId"));
  const occurredAt = params.get("occurredAt") ?? "";
  const result = useQuery({ queryKey: ["event", eventId, endpointId, occurredAt], queryFn: ({ signal }) => api.event(eventId, { endpointId, occurredAt }, signal), enabled: valid });
  const archiveNotReady = result.error instanceof ApiError && result.error.code === "ARCHIVE_NOT_READY";
  if (!valid) return <div className="page-stack"><Link className="back-link" to="/events"><ArrowLeft aria-hidden="true" size={15} />{t("events.stream")}</Link><EmptyState title={t("event.routingMissing")} message={t("event.routingDescription")} /><Link className="button" to="/events">{t("event.return")}</Link></div>;
  return <div className="page-stack">
    <Link className="back-link" to="/events"><ArrowLeft aria-hidden="true" size={15} />{t("events.stream")}</Link>
    {result.isPending ? <Skeleton rows={12} /> : null}
    {result.error ? <ErrorState archiveAction={archiveNotReady} error={result.error} {...(!archiveNotReady ? { onRetry: () => void result.refetch() } : {})} /> : null}
    {result.data ? <EventDetail event={result.data.data} /> : null}
  </div>;
}

function EventDetail({ event }: { event: import("../contracts").EventDetailDto }) {
  const { locale, t } = useI18n();
  const fields = [
    ["Event ID", <code>{event.eventId}</code>], [t("event.batchId"), <code>{event.batchId}</code>],
    ["Endpoint", <Link to={`/endpoints/${event.endpointId}`}>{event.hostname} · {event.endpointId}</Link>],
    ["Agent ID", <code>{event.agentId}</code>], [t("endpoints.operatingSystem"), event.osType], [t("endpoint.ipAddress"), displayNullable(event.ipAddress)],
    [t("event.occurred"), formatDateTime(event.occurredAt)], [t("event.ingested"), formatDateTime(event.ingestedAt)],
    [t("event.processName"), displayNullable(event.processName)], [t("event.processPath"), displayNullable(event.processPath)], ["PID", event.pid ?? t("common.notAvailable")], ["PPID", event.ppid ?? t("common.notAvailable")],
    [t("event.commandLine"), displayNullable(event.commandLine)], [t("event.user"), displayNullable(event.userName)],
    [t("event.filePath"), displayNullable(event.filePath)], [t("event.fileAction"), displayNullable(event.fileAction)], ["File SHA-256", displayNullable(event.fileHashSha256)],
    ["Remote IP", displayNullable(event.remoteIp)], [locale === "KO" ? "Remote Domain" : "Remote domain", displayNullable(event.remoteDomain)], [locale === "KO" ? "Remote Port" : "Remote port", event.remotePort ?? t("common.notAvailable")], ["Protocol", displayNullable(event.protocol)],
    ["DNS query", displayNullable(event.dnsQuery)], ["DNS record type", displayNullable(event.dnsRecordType)], ["DNS response", displayNullable(event.dnsResponseCode)], [t("event.dnsAnswers"), event.dnsAnswers.length ? event.dnsAnswers.join(", ") : t("common.none")],
    ["L7 protocol", displayNullable(event.l7Protocol)], ["HTTP method", displayNullable(event.httpMethod)], ["HTTP host", displayNullable(event.httpHost)], ["URL", displayNullable(event.url)], ["HTTP status", event.httpStatusCode ?? t("common.notAvailable")], ["HTTP user agent", displayNullable(event.httpUserAgent)],
    ["TLS SNI", displayNullable(event.tlsSni)], ["TLS version", displayNullable(event.tlsVersion)], ["TLS subject", displayNullable(event.tlsCertificateSubject)], ["TLS issuer", displayNullable(event.tlsCertificateIssuer)], ["TLS SHA-256", displayNullable(event.tlsCertificateSha256)],
  ] as const;
  return <>
    <PageHeader eyebrow={`EVENT · SCHEMA V${event.schemaVersion}`} title={event.processName ?? event.remoteDomain ?? event.filePath ?? event.eventType} description={event.eventId} actions={<StatusPill value={event.eventType} />} />
    <section className="detail-grid">
      <Panel className="wide" title={t("event.normalized")} subtitle={t("event.normalizedSubtitle")}><DefinitionGrid items={fields.map(([label, value]) => ({ label, value }))} /></Panel>
      <Panel title={t("event.payloadIdentity")} subtitle={t("event.payloadSubtitle")}><DefinitionGrid items={[{ label: t("event.payloadSha"), value: <code>{event.payloadSha256}</code> }, { label: t("event.schemaVersion"), value: event.schemaVersion }]} /></Panel>
      <Panel className="wide" title={t("event.rawPayload")} subtitle={t("event.rawPayloadSubtitle")}><pre className="json-view">{JSON.stringify(event.rawPayload, null, 2)}</pre></Panel>
    </section>
  </>;
}
