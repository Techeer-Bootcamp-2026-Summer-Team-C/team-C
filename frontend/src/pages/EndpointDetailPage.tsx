import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { EndpointSwitcher } from "../components/EndpointSwitcher";
import { DataTable, DetailLedger, DetailLedgerSection, EmptyState, ErrorState, PageHeader, RiskFactorList, Skeleton, StatusPill } from "../components/ui";
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

export function EndpointDetail({ endpoint }: { endpoint: EndpointDetailDto }) {
  const { t } = useI18n();
  const certificates = [...endpoint.certificates].sort((left, right) => Number(right.isRevoked || right.isExpired) - Number(left.isRevoked || left.isExpired) || right.issuedAt.localeCompare(left.issuedAt));
  return <>
    <PageHeader eyebrow={`ENDPOINT ${endpoint.endpointId}`} title={endpoint.hostname} description={endpoint.agentId} actions={<><StatusPill value={endpoint.status} /><StatusPill value={endpoint.risk.level} /></>} />
    {endpoint.isStale ? <div className="stale-warning" role="alert">{t("endpoint.staleWarning", { time: formatDateTime(endpoint.lastSeenAt) })}</div> : null}
    <section aria-label={t("endpoint.relatedEvidence")} className="endpoint-command-strip">
      <div className="endpoint-command-identity"><span>Endpoint</span><strong>{endpoint.hostname}</strong><small>{displayNullable(endpoint.ipAddress)} · {endpoint.osType} {displayNullable(endpoint.osVersion)}</small></div>
      <div className="endpoint-command-risk"><span>Risk</span><strong>{endpoint.risk.score} / 100</strong><small>{endpoint.risk.level} · {formatDateTime(endpoint.risk.calculatedAt)}</small></div>
      <div className="endpoint-command-evidence"><span>{t("endpoint.relatedEvidence")}</span><div className="endpoint-evidence-links">
        <Link to={`/alerts?endpointId=${endpoint.endpointId}&status=OPEN`}><strong>{endpoint.risk.activeAlertCount}</strong><span>{t("endpoints.activeAlerts")}</span></Link>
        <Link to={`/incidents?endpointId=${endpoint.endpointId}&status=OPEN`}><strong>{endpoint.risk.openIncidentCount}</strong><span>{t("endpoints.openIncidents")}</span></Link>
        <Link to={`/events?endpointId=${endpoint.endpointId}`}><strong>Event</strong><span>{t("endpoint.recentEvents")}</span></Link>
      </div><Link className="endpoint-process-entry" to={`/events?endpointId=${endpoint.endpointId}`}>{t("event.processTree")} · {t("endpoint.chooseEvent")}</Link></div>
    </section>
    <DetailLedger className="endpoint-detail-ledger">
      <DetailLedgerSection title="Endpoint Risk" subtitle={t("endpoint.calculated", { time: formatDateTime(endpoint.risk.calculatedAt) })} items={[
        { label: t("endpoint.level"), value: <StatusPill value={endpoint.risk.level} /> },
        { label: t("endpoints.activeAlerts"), value: endpoint.risk.activeAlertCount },
        { label: t("endpoints.openIncidents"), value: endpoint.risk.openIncidentCount },
        { label: t("endpoint.highestAlertScore"), value: endpoint.risk.highestAlertRiskScore ?? t("common.notAvailable") },
      ]}><RiskFactorList risk={endpoint.risk} /></DetailLedgerSection>
      <DetailLedgerSection title={t("endpoint.sensorHealth")} subtitle={t("endpoint.heartbeatSubtitle")}>{endpoint.sensorHealth.length ? <div className="sensor-ledger">{endpoint.sensorHealth.map((sensor) => <div className="sensor-ledger-row" key={sensor.sensor}><strong>{sensor.sensor}</strong><StatusPill value={sensor.status} /><span>{t("endpoint.provider")}: {displayNullable(sensor.provider)}</span><span>{t("endpoint.packetDrops")}: {sensor.packetDropCount ?? t("common.notAvailable")}</span><span>{t("endpoint.parseErrors")}: {sensor.parseErrorCount ?? t("common.notAvailable")}</span></div>)}</div> : <EmptyState title={t("endpoint.noSensor")} message={t("endpoint.noSensorDescription")} />}</DetailLedgerSection>
      <DetailLedgerSection title={t("endpoint.profile")} subtitle={t("endpoint.profileSubtitle")} items={[
        { label: "Agent ID", value: <code>{endpoint.agentId}</code> },
        { label: t("endpoints.operatingSystem"), value: `${endpoint.osType} · ${displayNullable(endpoint.osVersion)}` },
        { label: t("endpoint.ipAddress"), value: displayNullable(endpoint.ipAddress) },
        { label: t("endpoint.agentVersion"), value: displayNullable(endpoint.agentVersion) },
        { label: t("endpoint.buildId"), value: displayNullable(endpoint.agentBuildId) },
        { label: t("endpoint.architecture"), value: displayNullable(endpoint.agentArch) },
        { label: t("endpoints.lastSeen"), value: formatDateTime(endpoint.lastSeenAt) },
        { label: t("endpoints.registered"), value: formatDateTime(endpoint.registeredAt) },
        { label: t("endpoint.capabilities"), value: endpoint.capabilityCodes.length ? endpoint.capabilityCodes.join(", ") : t("common.noneReported") },
      ]} />
      <DetailLedgerSection title={t("endpoint.certificateHistory")} subtitle={t("endpoint.certificateSubtitle")}>{certificates.length ? <div className="certificate-history-table"><DataTable label={t("endpoint.certificateHistory")}><thead><tr><th scope="col">Fingerprint</th><th scope="col">{t("filter.status")}</th><th scope="col">{t("endpoint.subject")}</th><th scope="col">{t("endpoint.issued")}</th><th scope="col">{t("endpoint.expires")}</th><th scope="col">{t("endpoint.revoked")}</th></tr></thead><tbody>{certificates.map((certificate) => {
        const status = certificateStatus(certificate);
        const anomaly = certificate.isRevoked || certificate.isExpired;
        return <tr key={`${certificate.certFingerprint}-${certificate.issuedAt}`}><td><code>{certificate.certFingerprint}</code></td><td><div className="certificate-status-cell"><StatusPill value={status} />{anomaly ? <small>{t("endpoint.certificateAnomaly")}</small> : null}</div></td><td><div className="certificate-identity-cell"><span>{certificate.certSubject}</span><small>{t("endpoint.sanAgentId")}: <code>{certificate.certSanAgentId}</code></small></div></td><td>{formatDateTime(certificate.issuedAt)}</td><td>{formatDateTime(certificate.expiresAt)}</td><td>{formatDateTime(certificate.revokedAt)}</td></tr>;
      })}</tbody></DataTable></div> : <EmptyState title={t("endpoint.noCertificates")} message={t("endpoint.noCertificatesDescription")} />}</DetailLedgerSection>
    </DetailLedger>
  </>;
}

export function CertificateCard({ certificate }: { certificate: CertificateDto }) {
  const { t } = useI18n();
  const anomaly = certificate.isRevoked || certificate.isExpired;
  const status = certificateStatus(certificate);
  return <article aria-label={`${certificate.certFingerprint} ${status}`} className={anomaly ? "compact-card certificate-card anomalous" : "compact-card certificate-card"}><div><code>{certificate.certFingerprint}</code><StatusPill value={status} /></div>{anomaly ? <strong className="certificate-warning">{t("endpoint.certificateAnomaly")}</strong> : null}<dl><dt>{t("endpoint.subject")}</dt><dd>{certificate.certSubject}</dd><dt>{t("endpoint.sanAgentId")}</dt><dd>{certificate.certSanAgentId}</dd><dt>{t("endpoint.issued")}</dt><dd>{formatDateTime(certificate.issuedAt)}</dd><dt>{t("endpoint.expires")}</dt><dd>{formatDateTime(certificate.expiresAt)}</dd><dt>{t("endpoint.revoked")}</dt><dd>{formatDateTime(certificate.revokedAt)}</dd></dl></article>;
}

function certificateStatus(certificate: CertificateDto): "REVOKED" | "EXPIRED" | "ACTIVE" {
  return certificate.isRevoked ? "REVOKED" : certificate.isExpired ? "EXPIRED" : "ACTIVE";
}
