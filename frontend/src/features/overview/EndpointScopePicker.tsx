import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronLeft, ChevronRight, Monitor, Search } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { api } from "../../api/endpoints";
import type { EndpointDto } from "../../contracts";
import { useI18n } from "../../i18n/LocaleContext";
import { StatusPill } from "../../components/ui";

const PAGE_SIZE = 20;

export function EndpointScopePicker({ selectedEndpointId, onChange }: {
  selectedEndpointId: number | undefined;
  onChange: (endpointId: number | undefined) => void;
}) {
  const { t } = useI18n();
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [activeIndex, setActiveIndex] = useState(-1);
  const term = query.trim();
  const searchResult = useQuery({
    queryKey: ["overview-endpoint-search", term, page],
    queryFn: ({ signal }) => api.endpoints({ page, size: PAGE_SIZE, ...(term ? { q: term } : {}), sortBy: "riskScore", sortOrder: "desc" }, signal),
    enabled: open,
    staleTime: 30_000,
  });
  const selectedResult = useQuery({
    queryKey: ["overview-selected-endpoint", selectedEndpointId],
    queryFn: ({ signal }) => api.endpoints({ endpointIds: [selectedEndpointId as number], page: 1, size: 1 }, signal),
    enabled: selectedEndpointId !== undefined,
    staleTime: 30_000,
  });
  const endpoints = searchResult.data?.data.items ?? [];
  const selectedEndpoint = selectedResult.data?.data.items[0];
  const totalPages = Math.max(1, Math.ceil((searchResult.data?.data.total ?? 0) / PAGE_SIZE));

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const closeOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) close(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [open]);

  const select = (endpoint: EndpointDto | undefined) => {
    onChange(endpoint?.endpointId);
    close();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (!endpoints.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % endpoints.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => index <= 0 ? endpoints.length - 1 : index - 1);
    } else if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      select(endpoints[activeIndex]);
    }
  };

  return <div className="overview-endpoint-picker" ref={rootRef}>
    <button aria-expanded={open} aria-haspopup="dialog" aria-label={t("overview.endpointScope")} className="overview-endpoint-trigger" onClick={() => setOpen((value) => !value)} ref={triggerRef} type="button">
      <Monitor aria-hidden="true" size={15} />
      <span>{selectedEndpoint ? `${selectedEndpoint.hostname} · ID ${selectedEndpoint.endpointId}` : selectedEndpointId ? `Endpoint ${selectedEndpointId}` : t("overview.allEndpoints")}</span>
      <ChevronDown aria-hidden="true" size={14} />
    </button>
    {open ? <section aria-label={t("overview.endpointScope")} className="overview-endpoint-popover" role="dialog">
      <div className="overview-endpoint-search"><Search aria-hidden="true" size={15} /><input
        aria-activedescendant={activeIndex >= 0 ? `${listId}-option-${activeIndex}` : undefined}
        aria-autocomplete="list"
        aria-controls={listId}
        aria-expanded="true"
        autoComplete="off"
        maxLength={128}
        onChange={(event) => { setQuery(event.target.value); setPage(1); setActiveIndex(-1); }}
        onKeyDown={onKeyDown}
        placeholder={t("endpoints.search")}
        ref={inputRef}
        role="combobox"
        value={query}
      /></div>
      <div aria-busy={searchResult.isFetching} id={listId} role="listbox">
        <button aria-selected={selectedEndpointId === undefined} className="overview-endpoint-option" onClick={() => select(undefined)} role="option" type="button"><strong>{t("overview.allEndpoints")}</strong></button>
        {searchResult.isPending ? <p role="status">{t("common.loading")}</p> : null}
        {searchResult.error ? <p role="alert">{t("endpoint.switcherError")}</p> : null}
        {!searchResult.isPending && !searchResult.error && !endpoints.length ? <p>{t("endpoint.switcherEmpty")}</p> : null}
        {endpoints.map((endpoint, index) => <button
          aria-selected={selectedEndpointId === endpoint.endpointId}
          className={activeIndex === index ? "overview-endpoint-option active" : "overview-endpoint-option"}
          id={`${listId}-option-${index}`}
          key={endpoint.endpointId}
          onClick={() => select(endpoint)}
          onMouseEnter={() => setActiveIndex(index)}
          role="option"
          type="button"
        ><span><strong>{endpoint.hostname}</strong><small>ID {endpoint.endpointId}</small></span><span><StatusPill value={endpoint.status} /><StatusPill value={endpoint.risk.level} /><b>{endpoint.risk.score}</b></span></button>)}
      </div>
      {searchResult.data && totalPages > 1 ? <div className="overview-endpoint-pagination">
        <button aria-label={t("pagination.previous")} disabled={page <= 1} onClick={() => { setPage((value) => value - 1); setActiveIndex(-1); }} type="button"><ChevronLeft aria-hidden="true" size={15} /></button>
        <span>{t("pagination.summary", { page, totalPages, total: searchResult.data.data.total })}</span>
        <button aria-label={t("pagination.next")} disabled={page >= totalPages} onClick={() => { setPage((value) => value + 1); setActiveIndex(-1); }} type="button"><ChevronRight aria-hidden="true" size={15} /></button>
      </div> : null}
    </section> : null}
  </div>;

  function close(restoreFocus = true) {
    setOpen(false);
    setActiveIndex(-1);
    if (restoreFocus) requestAnimationFrame(() => triggerRef.current?.focus());
  }
}
