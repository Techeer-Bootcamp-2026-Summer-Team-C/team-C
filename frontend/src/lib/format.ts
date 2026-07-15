import { translate } from "../i18n/translations";

let displayLocale: "en-US" | "ko-KR" = "en-US";

export function setDisplayLocale(locale: "en-US" | "ko-KR"): void {
  displayLocale = locale;
}

export function formatDateTime(value: string | null): string {
  if (value === null) return translate(displayLocale === "ko-KR" ? "KO" : "EN", "common.notAvailable");
  return new Intl.DateTimeFormat(displayLocale, {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value));
}

export function formatCompactDate(value: string): string {
  return new Intl.DateTimeFormat(displayLocale, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function humanize(value: string): string {
  return value.toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

export function displayNullable(value: string | number | null): string {
  return value === null ? translate(displayLocale === "ko-KR" ? "KO" : "EN", "common.notAvailable") : String(value);
}
