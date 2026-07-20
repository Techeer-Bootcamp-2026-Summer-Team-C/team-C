import { Check, ChevronDown, Copy, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useI18n } from "../i18n/LocaleContext";

export function RawPayloadViewer({ payload }: { payload: Record<string, unknown> }) {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [copied, setCopied] = useState(false);
  const text = useMemo(() => JSON.stringify(payload, null, 2), [payload]);
  const lines = text.split("\n");
  const matchCount = query ? lines.reduce((count, line) => count + occurrences(line, query), 0) : 0;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return <details className="raw-payload-panel">
    <summary><span>{t("event.rawPayload")}</span><ChevronDown aria-hidden="true" size={17} /></summary>
    <div className="raw-payload-content">
      <div className="raw-payload-toolbar"><label><Search aria-hidden="true" size={15} /><span className="sr-only">{t("event.searchPayload")}</span><input onChange={(event) => setQuery(event.target.value)} placeholder={t("event.searchPayload")} type="search" value={query} /></label><span aria-live="polite">{query ? t("event.payloadMatches", { count: matchCount }) : ""}</span><button className="button secondary" onClick={() => void copy()} type="button">{copied ? <Check aria-hidden="true" size={15} /> : <Copy aria-hidden="true" size={15} />}{copied ? t("event.copied") : t("event.copyPayload")}</button></div>
      <pre aria-label={t("event.rawPayload")} className="json-view">{lines.map((line, index) => <span className={query && line.toLowerCase().includes(query.toLowerCase()) ? "json-line match" : "json-line"} key={`${index}-${line}`}>{highlight(line, query)}{"\n"}</span>)}</pre>
    </div>
  </details>;
}

function occurrences(value: string, query: string): number {
  const source = value.toLowerCase();
  const target = query.toLowerCase();
  let count = 0;
  let index = 0;
  while (target && (index = source.indexOf(target, index)) >= 0) {
    count += 1;
    index += target.length;
  }
  return count;
}

function highlight(value: string, query: string) {
  if (!query) return value;
  const index = value.toLowerCase().indexOf(query.toLowerCase());
  if (index < 0) return value;
  return <>{value.slice(0, index)}<mark>{value.slice(index, index + query.length)}</mark>{value.slice(index + query.length)}</>;
}
