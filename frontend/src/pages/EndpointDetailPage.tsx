import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { EndpointSwitcher } from "../components/EndpointSwitcher";
import { DefinitionGrid, EmptyState, ErrorState, PageHeader, Panel, RiskFactorList, Skeleton, StatusPill } from "../components/ui";
import type { CertificateDto, EndpointDetailDto } from "../contracts";
import { useI18n } from "../i18n/LocaleContext";
import { displayNullable, formatDateTime } from "../lib/format";

export function EndpointDetailPage() {
  const { t } = useI18n();
  const endpointId = Number(useParams().endpointId);
  const [params] = useSearchParams();
  const valid = Number.isInteger(endpointId) && endpointId > 0;
  const result = useQuery({ queryKey: ["endpoint", endpointId], queryFn: ({ signal }) => api.endpoint(endpointId, signal), enabled: valid });
  if (!valid) return <ErrorState error={new Error("The Endpoint ID is invalid.")} />;
  return <div className="page-stack">
    <Link className="back-link" to={`/endpoints${params.size ? `?${params}` : ""}`}><ArrowLeft aria-hidden="true" size={15} />{t("endpoints.inventory")}</Link>
    <EndpointSwitcher currentEndpointId={endpointId} params={params} />
    {result.isPending ? <Skeleton rows={10} /> : null}
    {result.error ? <ErrorState error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.data ? <EndpointDetail endpoint={result.data.data} /> : null}
  </div>;
}

function EndpointDetail({ endpoint }: { endpoint: EndpointDetailDto }) {
  const { t } = useI18n();
  const certificates = [...endpoint.certificates].sort((left, right) => Number(right.isRevoked || right.isExpired) - Number(left.isRevoked || left.isExpired) || right.issuedAt.localeCompare(left.issuedAt));
  return <>
    <PageHeader eyebrow={`ENDPOINT ${endpoint.endpointId}`} title={endpoint.hostname} description={endpoint.agentId} actions={<><StatusPill value={endpoint.status} /><StatusPill value={endpoint.risk.level} /></>} />
    {endpoint.isStale ? <div className="stale-warning" role="alert">{t("endpoint.staleWarning", { time: formatDateTime(endpoint.lastSeenAt) })}</div> : null}
    <section className="detail-grid endpoint-detail-grid">
      <Panel title="Endpoint Risk" subtitle={t("endpoint.calculated", { time: formatDateTime(endpoint.risk.calculatedAt) })} meta={<strong className="risk-large">{endpoint.risk.score} / 100</strong>}><DefinitionGrid items={[
        { label: t("endpoint.level"), value: <StatusPill value={endpoint.risk.level} /> },
        { label: t("endpoints.activeAlerts"), value: endpoint.risk.activeAlertCount },
        { label: t("endpoints.openIncidents"), value: endpoint.risk.openIncidentCount },
        { label: t("endpoint.highestAlertScore"), value: endpoint.risk.highestAlertRiskScore ?? t("common.notAvailable") },
      ]} /><RiskFactorList risk={endpoint.risk} /></Panel>
      <Panel title={t("endpoint.relatedEvidence")} subtitle={t("endpoint.relatedEvidenceSubtitle")}><div className="endpoint-evidence-links">
        <Link to={`/alerts?endpointId=${endpoint.endpointId}&status=OPEN`}><strong>{endpoint.risk.activeAlertCount}</strong><span>{t("endpoints.activeAlerts")}</span></Link>
        <Link to={`/incidents?endpointId=${endpoint.endpointId}&status=OPEN`}><strong>{endpoint.risk.openIncidentCount}</strong><span>{t("endpoints.openIncidents")}</span></Link>
        <Link to={`/events?endpointId=${endpoint.endpointId}`}><strong>Event</strong><span>{t("endpoint.recentEvents")}</span></Link>
      </div><div className="process-tree-entry"><strong>{t("event.processTree")}</strong><p>{t("endpoint.processTreeEntry")}</p><Link className="button secondary" to={`/events?endpointId=${endpoint.endpointId}`}>{t("endpoint.chooseEvent")}</Link></div></Panel>
      <Panel title={t("endpoint.sensorHealth")} subtitle={t("endpoint.heartbeatSubtitle")}>{endpoint.sensorHealth.length ? <div className="card-list">{endpoint.sensorHealth.map((sensor) => <article className="compact-card" key={sensor.sensor}><div><strong>{sensor.sensor}</strong><StatusPill value={sensor.status} /></div><dl><dt>{t("endpoint.provider")}</dt><dd>{displayNullable(sensor.provider)}</dd><dt>{t("endpoint.packetDrops")}</dt><dd>{sensor.packetDropCount ?? t("common.notAvailable")}</dd><dt>{t("endpoint.parseErrors")}</dt><dd>{sensor.parseErrorCount ?? t("common.notAvailable")}</dd></dl></article>)}</div> : <EmptyState title={t("endpoint.noSensor")} message={t("endpoint.noSensorDescription")} />}</Panel>
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
      <Panel className="wide" title={t("endpoint.certificateHistory")} subtitle={t("endpoint.certificateSubtitle")}>{certificates.length ? <div className="certificate-grid">{certificates.map((certificate) => <CertificateCard certificate={certificate} key={`${certificate.certFingerprint}-${certificate.issuedAt}`} />)}</div> : <EmptyState title={t("endpoint.noCertificates")} message={t("endpoint.noCertificatesDescription")} />}</Panel>
    </section>
  </>;
}

export function CertificateCard({ certificate }: { certificate: CertificateDto }) {
  const { t } = useI18n();
  const anomaly = certificate.isRevoked || certificate.isExpired;
  const status = certificate.isRevoked ? "REVOKED" : certificate.isExpired ? "EXPIRED" : "ACTIVE";
  return <article aria-label={`${certificate.certFingerprint} ${status}`} className={anomaly ? "compact-card certificate-card anomalous" : "compact-card certificate-card"}><div><code>{certificate.certFingerprint}</code><StatusPill value={status} /></div>{anomaly ? <strong className="certificate-warning">{t("endpoint.certificateAnomaly")}</strong> : null}<dl><dt>{t("endpoint.subject")}</dt><dd>{certificate.certSubject}</dd><dt>{t("endpoint.sanAgentId")}</dt><dd>{certificate.certSanAgentId}</dd><dt>{t("endpoint.issued")}</dt><dd>{formatDateTime(certificate.issuedAt)}</dd><dt>{t("endpoint.expires")}</dt><dd>{formatDateTime(certificate.expiresAt)}</dd><dt>{t("endpoint.revoked")}</dt><dd>{formatDateTime(certificate.revokedAt)}</dd></dl></article>;
}
