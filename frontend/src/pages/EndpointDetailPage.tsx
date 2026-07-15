import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { DefinitionGrid, EmptyState, ErrorState, PageHeader, Panel, RiskFactorList, Skeleton, StatusPill } from "../components/ui";
import { displayNullable, formatDateTime } from "../lib/format";
import { useI18n } from "../i18n/LocaleContext";

export function EndpointDetailPage() {
  const { t } = useI18n();
  const endpointId = Number(useParams().endpointId);
  const valid = Number.isInteger(endpointId) && endpointId > 0;
  const result = useQuery({ queryKey: ["endpoint", endpointId], queryFn: ({ signal }) => api.endpoint(endpointId, signal), enabled: valid });
  if (!valid) return <ErrorState error={new Error("The Endpoint ID is invalid.")} />;
  return <div className="page-stack">
    <Link className="back-link" to="/endpoints"><ArrowLeft aria-hidden="true" size={15} />{t("endpoints.inventory")}</Link>
    {result.isPending ? <Skeleton rows={10} /> : null}
    {result.error ? <ErrorState error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.data ? <EndpointDetail endpoint={result.data.data} /> : null}
  </div>;
}

function EndpointDetail({ endpoint }: { endpoint: import("../contracts").EndpointDetailDto }) {
  const { t } = useI18n();
  return <>
    <PageHeader eyebrow={`ENDPOINT ${endpoint.endpointId}`} title={endpoint.hostname} description={endpoint.agentId} actions={<><StatusPill value={endpoint.status} /><StatusPill value={endpoint.risk.level} /></>} />
    {endpoint.isStale ? <div className="stale-warning" role="alert">{t("endpoint.staleWarning", { time: formatDateTime(endpoint.lastSeenAt) })}</div> : null}
    <section className="detail-grid">
      <Panel title={t("endpoint.profile")} subtitle={t("endpoint.profileSubtitle")}><DefinitionGrid items={[
        { label: "Agent ID", value: <code>{endpoint.agentId}</code> },
        { label: t("endpoints.operatingSystem"), value: `${endpoint.osType} · ${displayNullable(endpoint.osVersion)}` },
        { label: t("endpoint.ipAddress"), value: displayNullable(endpoint.ipAddress) },
        { label: t("endpoint.agentVersion"), value: displayNullable(endpoint.agentVersion) },
        { label: t("endpoint.buildId"), value: displayNullable(endpoint.agentBuildId) },
        { label: t("endpoint.architecture"), value: displayNullable(endpoint.agentArch) },
        { label: t("endpoints.lastSeen"), value: formatDateTime(endpoint.lastSeenAt) },
        { label: t("endpoints.registered"), value: formatDateTime(endpoint.registeredAt) },
        { label: t("endpoint.capabilities"), value: endpoint.capabilityCodes.length ? endpoint.capabilityCodes.join(", ") : t("common.noneReported") },
      ]} /></Panel>
      <Panel title="Endpoint Risk" subtitle={t("endpoint.calculated", { time: formatDateTime(endpoint.risk.calculatedAt) })} meta={<strong className="risk-large">{endpoint.risk.score} / 100</strong>}><DefinitionGrid items={[
        { label: t("endpoint.level"), value: <StatusPill value={endpoint.risk.level} /> },
        { label: t("endpoints.activeAlerts"), value: endpoint.risk.activeAlertCount },
        { label: t("endpoints.openIncidents"), value: endpoint.risk.openIncidentCount },
        { label: t("endpoint.highestAlertScore"), value: endpoint.risk.highestAlertRiskScore ?? t("common.notAvailable") },
      ]} /><RiskFactorList risk={endpoint.risk} /></Panel>
      <Panel title={t("endpoint.sensorHealth")} subtitle={t("endpoint.heartbeatSubtitle")}>{endpoint.sensorHealth.length ? <div className="card-list">{endpoint.sensorHealth.map((sensor) => <article className="compact-card" key={sensor.sensor}><div><strong>{sensor.sensor}</strong><StatusPill value={sensor.status} /></div><dl><dt>{t("endpoint.provider")}</dt><dd>{displayNullable(sensor.provider)}</dd><dt>{t("endpoint.packetDrops")}</dt><dd>{sensor.packetDropCount ?? t("common.notAvailable")}</dd><dt>{t("endpoint.parseErrors")}</dt><dd>{sensor.parseErrorCount ?? t("common.notAvailable")}</dd></dl></article>)}</div> : <EmptyState title={t("endpoint.noSensor")} message={t("endpoint.noSensorDescription")} />}</Panel>
      <Panel title={t("endpoint.certificateHistory")} subtitle={t("endpoint.certificateSubtitle")}>{endpoint.certificates.length ? <div className="card-list">{endpoint.certificates.map((certificate) => <article className="compact-card" key={`${certificate.certFingerprint}-${certificate.issuedAt}`}><div><code>{certificate.certFingerprint}</code>{certificate.isRevoked ? <StatusPill value="REVOKED" /> : certificate.isExpired ? <StatusPill value="EXPIRED" /> : <StatusPill value="ACTIVE" />}</div><dl><dt>{t("endpoint.subject")}</dt><dd>{certificate.certSubject}</dd><dt>{t("endpoint.sanAgentId")}</dt><dd>{certificate.certSanAgentId}</dd><dt>{t("endpoint.issued")}</dt><dd>{formatDateTime(certificate.issuedAt)}</dd><dt>{t("endpoint.expires")}</dt><dd>{formatDateTime(certificate.expiresAt)}</dd><dt>{t("endpoint.revoked")}</dt><dd>{formatDateTime(certificate.revokedAt)}</dd></dl></article>)}</div> : <EmptyState title={t("endpoint.noCertificates")} message={t("endpoint.noCertificatesDescription")} />}</Panel>
    </section>
  </>;
}
