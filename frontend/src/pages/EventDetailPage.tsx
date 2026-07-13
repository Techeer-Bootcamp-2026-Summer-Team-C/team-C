import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { api } from "../api/endpoints";
import { DefinitionGrid, EmptyState, ErrorState, PageHeader, Panel, Skeleton, StatusPill } from "../components/ui";
import { displayNullable, formatDateTime } from "../lib/format";
import { validEventDetailQuery } from "../lib/url";

export function EventDetailPage() {
  const eventId = useParams().eventId ?? "";
  const [params] = useSearchParams();
  const valid = Boolean(eventId) && validEventDetailQuery(params);
  const endpointId = Number(params.get("endpointId"));
  const occurredAt = params.get("occurredAt") ?? "";
  const result = useQuery({ queryKey: ["event", eventId, endpointId, occurredAt], queryFn: ({ signal }) => api.event(eventId, { endpointId, occurredAt }, signal), enabled: valid });
  const archiveNotReady = result.error instanceof ApiError && result.error.code === "ARCHIVE_NOT_READY";
  if (!valid) return <div className="page-stack"><Link className="back-link" to="/events"><ArrowLeft aria-hidden="true" size={15} />Event stream</Link><EmptyState title="Event routing information is missing" message="Open this Event from the Event list so endpointId and occurredAt remain in the URL query." /><Link className="button" to="/events">Return to Events</Link></div>;
  return <div className="page-stack">
    <Link className="back-link" to="/events"><ArrowLeft aria-hidden="true" size={15} />Event stream</Link>
    {result.isPending ? <Skeleton rows={12} /> : null}
    {result.error ? <ErrorState archiveAction={archiveNotReady} error={result.error} {...(!archiveNotReady ? { onRetry: () => void result.refetch() } : {})} /> : null}
    {result.data ? <EventDetail event={result.data.data} /> : null}
  </div>;
}

function EventDetail({ event }: { event: import("../contracts").EventDetailDto }) {
  const fields = [
    ["Event ID", <code>{event.eventId}</code>], ["Batch ID", <code>{event.batchId}</code>],
    ["Endpoint", <Link to={`/endpoints/${event.endpointId}`}>{event.hostname} · {event.endpointId}</Link>],
    ["Agent ID", <code>{event.agentId}</code>], ["Operating system", event.osType], ["IP address", displayNullable(event.ipAddress)],
    ["Occurred", formatDateTime(event.occurredAt)], ["Ingested", formatDateTime(event.ingestedAt)],
    ["Process name", displayNullable(event.processName)], ["Process path", displayNullable(event.processPath)], ["PID", event.pid ?? "Not available"], ["PPID", event.ppid ?? "Not available"],
    ["Command line", displayNullable(event.commandLine)], ["User", displayNullable(event.userName)],
    ["File path", displayNullable(event.filePath)], ["File action", displayNullable(event.fileAction)], ["File SHA-256", displayNullable(event.fileHashSha256)],
    ["Remote IP", displayNullable(event.remoteIp)], ["Remote domain", displayNullable(event.remoteDomain)], ["Remote port", event.remotePort ?? "Not available"], ["Protocol", displayNullable(event.protocol)],
    ["DNS query", displayNullable(event.dnsQuery)], ["DNS record type", displayNullable(event.dnsRecordType)], ["DNS response", displayNullable(event.dnsResponseCode)], ["DNS answers", event.dnsAnswers.length ? event.dnsAnswers.join(", ") : "None"],
    ["L7 protocol", displayNullable(event.l7Protocol)], ["HTTP method", displayNullable(event.httpMethod)], ["HTTP host", displayNullable(event.httpHost)], ["URL", displayNullable(event.url)], ["HTTP status", event.httpStatusCode ?? "Not available"], ["HTTP user agent", displayNullable(event.httpUserAgent)],
    ["TLS SNI", displayNullable(event.tlsSni)], ["TLS version", displayNullable(event.tlsVersion)], ["TLS subject", displayNullable(event.tlsCertificateSubject)], ["TLS issuer", displayNullable(event.tlsCertificateIssuer)], ["TLS SHA-256", displayNullable(event.tlsCertificateSha256)],
  ] as const;
  return <>
    <PageHeader eyebrow={`EVENT · SCHEMA V${event.schemaVersion}`} title={event.processName ?? event.remoteDomain ?? event.filePath ?? event.eventType} description={event.eventId} actions={<StatusPill value={event.eventType} />} />
    <section className="detail-grid">
      <Panel className="wide" title="Normalized event" subtitle="Required and nullable Event DTO fields"><DefinitionGrid items={fields.map(([label, value]) => ({ label, value }))} /></Panel>
      <Panel title="Payload identity" subtitle="No packet or PCAP bytes"><DefinitionGrid items={[{ label: "Payload SHA-256", value: <code>{event.payloadSha256}</code> }, { label: "Schema version", value: event.schemaVersion }]} /></Panel>
      <Panel className="wide" title="Raw payload" subtitle="Normalized metadata event JSON"><pre className="json-view">{JSON.stringify(event.rawPayload, null, 2)}</pre></Panel>
    </section>
  </>;
}
