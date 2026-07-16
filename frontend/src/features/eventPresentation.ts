import type { EventDetailDto, EventDto } from "../contracts";

export type EventDetailGroup = "IDENTITY" | "PROCESS" | "FILE" | "NETWORK" | "DNS" | "HTTP_TLS";

export function eventDetailGroups(event: EventDetailDto): EventDetailGroup[] {
  const groups: EventDetailGroup[] = ["IDENTITY"];
  if (hasAny(event.processName, event.processPath, event.commandLine, event.pid, event.ppid, event.userName)) groups.push("PROCESS");
  if (event.eventType === "FILE_EVENT" || hasAny(event.filePath, event.fileAction, event.fileHashSha256)) groups.push("FILE");
  if (event.eventType === "NETWORK_CONNECTION" || hasAny(event.remoteIp, event.remoteDomain, event.remotePort, event.protocol)) groups.push("NETWORK");
  if (event.eventType === "DNS_QUERY" || hasAny(event.dnsQuery, event.dnsRecordType, event.dnsResponseCode) || event.dnsAnswers.length > 0) groups.push("DNS");
  if (event.eventType === "L7_EVENT" || hasAny(event.l7Protocol, event.httpMethod, event.httpHost, event.url, event.httpStatusCode, event.httpUserAgent, event.tlsSni, event.tlsVersion, event.tlsCertificateSubject, event.tlsCertificateIssuer, event.tlsCertificateSha256)) groups.push("HTTP_TLS");
  return groups;
}

export function eventListSummary(event: EventDto): string {
  switch (event.eventType) {
    case "PROCESS_EXECUTION": return [event.processName, event.commandLine].filter(Boolean).join(" · ");
    case "FILE_EVENT": return [event.fileAction, event.filePath].filter(Boolean).join(" · ");
    case "NETWORK_CONNECTION": return [event.protocol, event.remoteDomain ?? event.remoteIp, event.remotePort].filter((value) => value !== null && value !== "").join(" · ");
    case "DNS_QUERY": return [event.dnsQuery, event.dnsResponseCode].filter(Boolean).join(" · ");
    case "L7_EVENT": return [event.httpMethod, event.httpHost ?? event.remoteDomain, event.httpStatusCode ?? event.l7Protocol].filter((value) => value !== null && value !== "").join(" · ");
  }
}

function hasAny(...values: unknown[]): boolean {
  return values.some((value) => value !== null && value !== undefined && value !== "");
}
