import type { TranslationKey } from "./translations";
import type { TranslationParams } from "./types";

type Translate = (key: TranslationKey, params?: TranslationParams) => string;

interface RuleCopyKeys {
  ruleName: TranslationKey;
  title: TranslationKey;
  titleOnEndpoint: TranslationKey;
  summary: TranslationKey;
}

const RULE_KEYS: Readonly<Record<string, RuleCopyKeys>> = {
  PROC_POWERSHELL_ENCODED: {
    ruleName: "detection.procPowershellEncoded.ruleName",
    title: "detection.procPowershellEncoded.title",
    titleOnEndpoint: "detection.procPowershellEncoded.titleOnEndpoint",
    summary: "detection.procPowershellEncoded.summary",
  },
  NET_SUSPICIOUS_EGRESS: {
    ruleName: "detection.netSuspiciousEgress.ruleName",
    title: "detection.netSuspiciousEgress.title",
    titleOnEndpoint: "detection.netSuspiciousEgress.titleOnEndpoint",
    summary: "detection.netSuspiciousEgress.summary",
  },
  DNS_RARE_DOMAIN: {
    ruleName: "detection.dnsRareDomain.ruleName",
    title: "detection.dnsRareDomain.title",
    titleOnEndpoint: "detection.dnsRareDomain.titleOnEndpoint",
    summary: "detection.dnsRareDomain.summary",
  },
  FILE_SUSPICIOUS_DROP: {
    ruleName: "detection.fileSuspiciousDrop.ruleName",
    title: "detection.fileSuspiciousDrop.title",
    titleOnEndpoint: "detection.fileSuspiciousDrop.titleOnEndpoint",
    summary: "detection.fileSuspiciousDrop.summary",
  },
  L7_UPLOAD_ANOMALY: {
    ruleName: "detection.l7UploadAnomaly.ruleName",
    title: "detection.l7UploadAnomaly.title",
    titleOnEndpoint: "detection.l7UploadAnomaly.titleOnEndpoint",
    summary: "detection.l7UploadAnomaly.summary",
  },
};

const TITLE_KEYS: Readonly<Record<string, TranslationKey>> = {
  PROC_POWERSHELL_ENCODED: "detection.procPowershellEncoded.title",
  "PowerShell Encoded Command": "detection.procPowershellEncoded.ruleName",
  "Encoded PowerShell command detected": "detection.procPowershellEncoded.title",
  NET_SUSPICIOUS_EGRESS: "detection.netSuspiciousEgress.title",
  "Suspicious Egress Destination": "detection.netSuspiciousEgress.ruleName",
  "Suspicious encrypted egress detected": "detection.netSuspiciousEgress.title",
  DNS_RARE_DOMAIN: "detection.dnsRareDomain.title",
  "Rare Domain Query": "detection.dnsRareDomain.ruleName",
  "Rare domain query detected": "detection.dnsRareDomain.title",
  FILE_SUSPICIOUS_DROP: "detection.fileSuspiciousDrop.title",
  "Suspicious File Drop": "detection.fileSuspiciousDrop.ruleName",
  "Suspicious file drop detected": "detection.fileSuspiciousDrop.title",
  L7_UPLOAD_ANOMALY: "detection.l7UploadAnomaly.title",
  "Unusual HTTPS Upload": "detection.l7UploadAnomaly.ruleName",
  "Unusual HTTPS upload detected": "detection.l7UploadAnomaly.title",
};

const SUMMARY_KEYS: Readonly<Record<string, TranslationKey>> = {
  "PowerShell was executed with an encoded command argument.": "detection.procPowershellEncoded.summary",
  "A monitored process connected to a rare external destination.": "detection.netSuspiciousEgress.summary",
  "An endpoint queried a rarely observed domain.": "detection.dnsRareDomain.summary",
  "A process created a suspicious payload or artifact file.": "detection.fileSuspiciousDrop.summary",
  "An unusual upload request was observed to an external host.": "detection.l7UploadAnomaly.summary",
};

const TITLE_PREFIXES = [
  ["PowerShell Encoded Command on ", "PROC_POWERSHELL_ENCODED"],
  ["Encoded PowerShell Command on ", "PROC_POWERSHELL_ENCODED"],
  ["Suspicious Egress Destination on ", "NET_SUSPICIOUS_EGRESS"],
  ["Rare Domain Query on ", "DNS_RARE_DOMAIN"],
  ["Suspicious File Drop on ", "FILE_SUSPICIOUS_DROP"],
  ["Unusual HTTPS Upload on ", "L7_UPLOAD_ANOMALY"],
] as const;

const GUIDANCE_TITLE_KEYS: Readonly<Record<string, TranslationKey>> = {
  "Review domain and query process": "guidance.reviewDomainProcess",
  "Block confirmed malicious domain": "guidance.blockMaliciousDomain",
  "Validate file origin and hash": "guidance.validateFileOrigin",
  "Quarantine confirmed malicious file": "guidance.quarantineMaliciousFile",
  "Review upload context": "guidance.reviewUploadContext",
  "Restrict unauthorized upload path": "guidance.restrictUploadPath",
  "Review destination and source process": "guidance.reviewDestinationProcess",
  "Contain unauthorized egress": "guidance.containUnauthorizedEgress",
  "Review source event": "guidance.reviewSourceEvent",
};

export function detectionTitle(t: Translate, value: string, ruleCode?: string): string {
  const key = TITLE_KEYS[value];
  if (key) return t(key);
  for (const [prefix, code] of TITLE_PREFIXES) {
    const copy = RULE_KEYS[code];
    if (copy && value.startsWith(prefix)) return t(copy.titleOnEndpoint, { endpoint: value.slice(prefix.length) });
  }
  const ruleKey = ruleCode ? RULE_KEYS[ruleCode]?.title : undefined;
  return ruleKey ? t(ruleKey) : value;
}

export function detectionRuleName(t: Translate, value: string, ruleCode?: string): string {
  const ruleKey = ruleCode ? RULE_KEYS[ruleCode]?.ruleName : undefined;
  const key = ruleKey ?? TITLE_KEYS[value];
  return key ? t(key) : value;
}

export function detectionSummary(t: Translate, value: string | null | undefined, fallback: string): string {
  if (!value) return fallback;
  const key = SUMMARY_KEYS[value];
  if (key) return t(key);
  const qaAgentId = /^Deterministic long-range QA alert for (.+)\.$/.exec(value)?.[1];
  return qaAgentId ? t("detection.qaLongRange.summary", { agentId: qaAgentId }) : value;
}

export function responseGuidanceTitle(t: Translate, value: string): string {
  const key = GUIDANCE_TITLE_KEYS[value];
  return key ? t(key) : value;
}

export function riskFactorDescription(t: Translate, value: string): string {
  return value === "OPEN correlation Incident contribution" ? t("risk.openIncidentContribution") : value;
}
