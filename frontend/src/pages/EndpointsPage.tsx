import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { DataTable, EmptyState, ErrorState, Field, GlobalFilterBar, PageHeader, Pagination, Panel, Skeleton, StatusPill } from "../components/ui";
import type { EndpointListQuery } from "../contracts";
import { formatDateTime } from "../lib/format";
import { parseEndpointIds } from "../lib/endpointIds";
import { allowedValue } from "../lib/params";
import { numberParam, updateParams } from "../lib/url";

export function EndpointsPage() {
  const [params, setParams] = useSearchParams();
  const status = allowedValue(params.get("status"), ["ONLINE", "OFFLINE", "RETIRED"] as const);
  const osType = allowedValue(params.get("osType"), ["WINDOWS", "MACOS"] as const);
  const riskLevel = allowedValue(params.get("riskLevel"), ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const);
  const sortBy = allowedValue(params.get("sortBy"), ["riskScore", "lastSeenAt", "registeredAt"] as const) ?? "riskScore";
  const sortOrder = allowedValue(params.get("sortOrder"), ["asc", "desc"] as const) ?? "desc";
  const endpointIds = parseEndpointIds(params.get("endpointIds"));
  const query: EndpointListQuery = { page: numberParam(params, "page", 1), size: numberParam(params, "size", 50), sortBy, sortOrder };
  if (status) query.status = status;
  if (osType) query.osType = osType;
  if (riskLevel) query.riskLevel = riskLevel;
  if (endpointIds.length) query.endpointIds = endpointIds;
  const result = useQuery({ queryKey: ["endpoints", query], queryFn: ({ signal }) => api.endpoints(query, signal) });

  return <div className="page-stack">
    <PageHeader eyebrow="CURRENT SNAPSHOT" title="Endpoints" description="Endpoint health and Backend-calculated Risk, including retired assets." />
    <GlobalFilterBar hasFilters={params.size > 0} onClear={() => setParams({})}>
      <Field label="Endpoint IDs"><input onChange={(event) => setParams(updateParams(params, { endpointIds: event.target.value }))} placeholder="1, 2, 7" value={params.get("endpointIds") ?? ""} /></Field>
      <Field label="Status"><select onChange={(event) => setParams(updateParams(params, { status: event.target.value }))} value={status ?? ""}><option value="">All statuses</option><option>ONLINE</option><option>OFFLINE</option><option>RETIRED</option></select></Field>
      <Field label="Operating system"><select onChange={(event) => setParams(updateParams(params, { osType: event.target.value }))} value={osType ?? ""}><option value="">All systems</option><option>WINDOWS</option><option>MACOS</option></select></Field>
      <Field label="Risk level"><select onChange={(event) => setParams(updateParams(params, { riskLevel: event.target.value }))} value={riskLevel ?? ""}><option value="">All levels</option><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></Field>
      <Field label="Sort"><select onChange={(event) => setParams(updateParams(params, { sortBy: event.target.value }))} value={sortBy}><option value="riskScore">Risk score</option><option value="lastSeenAt">Last seen</option><option value="registeredAt">Registered</option></select></Field>
      <Field label="Order"><select onChange={(event) => setParams(updateParams(params, { sortOrder: event.target.value }))} value={sortOrder}><option value="desc">Descending</option><option value="asc">Ascending</option></select></Field>
    </GlobalFilterBar>
    {result.isPending ? <Skeleton rows={8} /> : null}
    {result.error ? <ErrorState error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.data ? <Panel title="Endpoint inventory" subtitle={`${result.data.data.total} Endpoint records`}>
      {result.data.data.items.length ? <><DataTable label="Endpoint inventory"><thead><tr><th scope="col">Endpoint</th><th scope="col">OS</th><th scope="col">Status</th><th scope="col">Last seen</th><th scope="col" aria-sort={sortBy === "riskScore" ? (sortOrder === "desc" ? "descending" : "ascending") : "none"}>Risk</th><th scope="col">Active Alerts</th><th scope="col">Open Incidents</th></tr></thead><tbody>{result.data.data.items.map((endpoint) => <tr key={endpoint.endpointId}><td><Link className="table-primary" to={`/endpoints/${endpoint.endpointId}`}><strong>{endpoint.hostname}</strong><code>{endpoint.agentId}</code></Link></td><td>{endpoint.osType}<small>{endpoint.osVersion ?? "Version unavailable"}</small></td><td><StatusPill value={endpoint.status} />{endpoint.isStale ? <span className="stale-inline">Stale</span> : null}</td><td>{formatDateTime(endpoint.lastSeenAt)}</td><td><Link className="risk-cell" to={`/endpoints/${endpoint.endpointId}`}><strong>{endpoint.risk.score}</strong><StatusPill value={endpoint.risk.level} /></Link></td><td>{endpoint.risk.activeAlertCount}</td><td>{endpoint.risk.openIncidentCount}</td></tr>)}</tbody></DataTable><Pagination page={result.data.data} /></> : <EmptyState title="No Endpoints found" message={params.size ? "No Endpoints match the current filters." : "No Endpoint has registered yet."} />}
    </Panel> : null}
  </div>;
}
