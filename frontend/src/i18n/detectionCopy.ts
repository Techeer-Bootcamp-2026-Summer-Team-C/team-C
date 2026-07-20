import type { TranslationKey } from "./translations";

type Translate = (key: TranslationKey) => string;

const TITLE_KEYS: Readonly<Record<string, TranslationKey>> = {
  PROC_POWERSHELL_ENCODED: "detection.procPowershellEncoded.title",
  "Encoded PowerShell command detected": "detection.procPowershellEncoded.title",
  NET_SUSPICIOUS_EGRESS: "detection.netSuspiciousEgress.title",
  "Suspicious encrypted egress detected": "detection.netSuspiciousEgress.title",
};

const SUMMARY_KEYS: Readonly<Record<string, TranslationKey>> = {
  "PowerShell was executed with an encoded command argument.": "detection.procPowershellEncoded.summary",
  "A monitored process connected to a rare external destination.": "detection.netSuspiciousEgress.summary",
};

export function detectionTitle(t: Translate, value: string, ruleCode?: string): string {
  const key = (ruleCode ? TITLE_KEYS[ruleCode] : undefined) ?? TITLE_KEYS[value];
  return key ? t(key) : value;
}

export function detectionSummary(t: Translate, value: string | null | undefined, fallback: string): string {
  if (!value) return fallback;
  const key = SUMMARY_KEYS[value];
  return key ? t(key) : value;
}
