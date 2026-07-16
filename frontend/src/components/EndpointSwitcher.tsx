import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useId, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/endpoints";
import type { EndpointDto } from "../contracts";
import { useI18n } from "../i18n/LocaleContext";
import { StatusPill } from "./ui";

export function EndpointSwitcher({ currentEndpointId, params }: { currentEndpointId: number; params: URLSearchParams }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const term = query.trim();
  const validTerm = term.length >= 1 && term.length <= 128;
  const result = useQuery({
    queryKey: ["endpoint-switcher", term, page],
    queryFn: ({ signal }) => api.endpoints({ q: term, page, size: 20, sortBy: "riskScore", sortOrder: "desc" }, signal),
    enabled: open && validTerm,
  });
  const endpoints = result.data?.data.items ?? [];
  const select = (endpoint: EndpointDto) => {
    const next = new URLSearchParams(params);
    next.set("selected", String(endpoint.endpointId));
    setOpen(false);
    void navigate({ pathname: `/endpoints/${endpoint.endpointId}`, search: `?${next}` });
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      setActiveIndex(-1);
      return;
    }
    if (!endpoints.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((value) => (value + 1) % endpoints.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((value) => (value <= 0 ? endpoints.length - 1 : value - 1));
    } else if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      const endpoint = endpoints[activeIndex];
      if (endpoint) select(endpoint);
    }
  };

  return <div className="endpoint-switcher">
    <label htmlFor={`${listId}-input`}>{t("endpoint.switcher")}</label>
    <div className="endpoint-switcher-input"><Search aria-hidden="true" size={16} /><input
      aria-activedescendant={activeIndex >= 0 ? `${listId}-option-${activeIndex}` : undefined}
      aria-autocomplete="list"
      aria-controls={listId}
      aria-expanded={open && validTerm}
      autoComplete="off"
      id={`${listId}-input`}
      onChange={(event) => { setQuery(event.target.value); setPage(1); setActiveIndex(-1); setOpen(true); }}
      onFocus={() => setOpen(validTerm)}
      onKeyDown={onKeyDown}
      placeholder={t("endpoint.switcherPlaceholder")}
      ref={inputRef}
      role="combobox"
      value={query}
    /></div>
    {open && validTerm ? <div className="endpoint-switcher-popover">
      <div aria-busy={result.isFetching} id={listId} role="listbox">
        {result.isPending ? <p role="status">{t("common.loading")}</p> : null}
        {result.error ? <p role="alert">{t("endpoint.switcherError")}</p> : null}
        {!result.isPending && !result.error && !endpoints.length ? <p>{t("endpoint.switcherEmpty")}</p> : null}
        {endpoints.map((endpoint, index) => <button
          aria-selected={activeIndex === index}
          className={activeIndex === index ? "endpoint-option active" : "endpoint-option"}
          id={`${listId}-option-${index}`}
          key={endpoint.endpointId}
          onClick={() => select(endpoint)}
          onMouseEnter={() => setActiveIndex(index)}
          role="option"
          tabIndex={-1}
          type="button"
        ><span><strong>{endpoint.hostname}</strong><small>ID {endpoint.endpointId} · {endpoint.agentId}</small></span><span><StatusPill value={endpoint.status} /><StatusPill value={endpoint.risk.level} /><b>{endpoint.risk.score}</b></span></button>)}
      </div>
      {result.data && result.data.data.total > result.data.data.size ? <div className="endpoint-switcher-pagination"><button aria-label={t("pagination.previous")} disabled={page <= 1} onClick={() => { setPage((value) => value - 1); setActiveIndex(-1); }} type="button"><ChevronLeft size={15} /></button><span>{page} / {Math.ceil(result.data.data.total / result.data.data.size)}</span><button aria-label={t("pagination.next")} disabled={page * result.data.data.size >= result.data.data.total} onClick={() => { setPage((value) => value + 1); setActiveIndex(-1); }} type="button"><ChevronRight size={15} /></button></div> : null}
    </div> : null}
    <span className="endpoint-switcher-current">{t("endpoint.current", { endpointId: currentEndpointId })}</span>
  </div>;
}
