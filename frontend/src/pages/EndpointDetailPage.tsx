import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { DefinitionGrid, EmptyState, ErrorState, PageHeader, Panel, RiskFactorList, Skeleton, StatusPill } from "../components/ui";
import { displayNullable, formatDateTime } from "../lib/format";

export function EndpointDetailPage() {
  const endpointId = Number(useParams().endpointId);
  const valid = Number.isInteger(endpointId) && endpointId > 0;
  const result = useQuery({ queryKey: ["endpoint", endpointId], queryFn: ({ signal }) => api.endpoint(endpointId, signal), enabled: valid });
  if (!valid) return <ErrorState error={new Error("The Endpoint ID is invalid.")} />;
  return <div className="page-stack">
    <Link className="back-link" to="/endpoints"><ArrowLeft aria-hidden="true" size={15} />Endpoint inventory</Link>
    {result.isPending ? <Skeleton rows={10} /> : null}
    {result.error ? <ErrorState error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.data ? <EndpointDetail endpoint={result.data.data} /> : null}
  </div>;
}

function EndpointDetail({ endpoint }: { endpoint: import("../contracts").EndpointDetailDto }) {
  return <>
    <PageHeader eyebrow={`ENDPOINT ${endpoint.endpointId}`} title={endpoint.hostname} description={endpoint.agentId} actions={<><StatusPill value={endpoint.status} /><StatusPill value={endpoint.risk.level} /></>} />
    {endpoint.isStale ? <div className="stale-warning" role="alert">This Endpoint snapshot is stale. Last seen {formatDateTime(endpoint.lastSeenAt)}.</div> : null}
    <section className="detail-grid">
      <Panel title="Endpoint profile" subtitle="Current Agent and platform snapshot"><DefinitionGrid items={[
        { label: "Agent ID", value: <code>{endpoint.agentId}</code> },
        { label: "Operating system", value: `${endpoint.osType} · ${displayNullable(endpoint.osVersion)}` },
        { label: "IP address", value: displayNullable(endpoint.ipAddress) },
        { label: "Agent version", value: displayNullable(endpoint.agentVersion) },
        { label: "Build ID", value: displayNullable(endpoint.agentBuildId) },
        { label: "Architecture", value: displayNullable(endpoint.agentArch) },
        { label: "Last seen", value: formatDateTime(endpoint.lastSeenAt) },
        { label: "Registered", value: formatDateTime(endpoint.registeredAt) },
        { label: "Capabilities", value: endpoint.capabilityCodes.length ? endpoint.capabilityCodes.join(", ") : "None reported" },
      ]} /></Panel>
      <Panel title="Endpoint Risk" subtitle={`Calculated ${formatDateTime(endpoint.risk.calculatedAt)}`} meta={<strong className="risk-large">{endpoint.risk.score} / 100</strong>}><DefinitionGrid items={[
        { label: "Level", value: <StatusPill value={endpoint.risk.level} /> },
        { label: "Active Alerts", value: endpoint.risk.activeAlertCount },
        { label: "Open Incidents", value: endpoint.risk.openIncidentCount },
        { label: "Highest Alert score", value: endpoint.risk.highestAlertRiskScore ?? "Not available" },
      ]} /><RiskFactorList risk={endpoint.risk} /></Panel>
      <Panel title="Sensor health" subtitle="Latest heartbeat snapshot">{endpoint.sensorHealth.length ? <div className="card-list">{endpoint.sensorHealth.map((sensor) => <article className="compact-card" key={sensor.sensor}><div><strong>{sensor.sensor}</strong><StatusPill value={sensor.status} /></div><dl><dt>Provider</dt><dd>{displayNullable(sensor.provider)}</dd><dt>Packet drops</dt><dd>{sensor.packetDropCount ?? "Not available"}</dd><dt>Parse errors</dt><dd>{sensor.parseErrorCount ?? "Not available"}</dd></dl></article>)}</div> : <EmptyState title="No sensor health" message="The Endpoint has not reported sensor snapshots." />}</Panel>
      <Panel title="Certificate history" subtitle="Public certificate identity only">{endpoint.certificates.length ? <div className="card-list">{endpoint.certificates.map((certificate) => <article className="compact-card" key={`${certificate.certFingerprint}-${certificate.issuedAt}`}><div><code>{certificate.certFingerprint}</code>{certificate.isRevoked ? <StatusPill value="REVOKED" /> : certificate.isExpired ? <StatusPill value="EXPIRED" /> : <StatusPill value="ACTIVE" />}</div><dl><dt>Subject</dt><dd>{certificate.certSubject}</dd><dt>SAN agent ID</dt><dd>{certificate.certSanAgentId}</dd><dt>Issued</dt><dd>{formatDateTime(certificate.issuedAt)}</dd><dt>Expires</dt><dd>{formatDateTime(certificate.expiresAt)}</dd><dt>Revoked</dt><dd>{formatDateTime(certificate.revokedAt)}</dd></dl></article>)}</div> : <EmptyState title="No certificate history" message="No certificate records are available for this Endpoint." />}</Panel>
    </section>
  </>;
}
