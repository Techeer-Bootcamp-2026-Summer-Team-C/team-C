import type { DashboardTimeQuery, TimePreset } from "../contracts";
import { useI18n } from "../i18n/LocaleContext";
import { intervalFor, localDateTimeValue, timePreset, updateParams, utcFromLocal } from "../lib/url";
import { Field } from "./ui";

export interface TimeFilterState {
  preset: TimePreset;
  from: string | undefined;
  to: string | undefined;
  valid: boolean;
  query: DashboardTimeQuery;
  interval: import("../contracts").DashboardInterval;
}

export function readTimeFilter(params: URLSearchParams): TimeFilterState {
  const rawPreset = params.get("timePreset");
  const preset = timePreset(params);
  const from = params.get("from") ?? undefined;
  const to = params.get("to") ?? undefined;
  const presetValid = rawPreset === null || ["LATEST_15M", "LATEST_1H", "LATEST_24H", "LATEST_7D", "CUSTOM"].includes(rawPreset);
  const valid = presetValid && (preset !== "CUSTOM" || Boolean(from && to && Date.parse(from) < Date.parse(to)));
  const query: DashboardTimeQuery = { timePreset: preset };
  if (preset === "CUSTOM" && from && to) {
    query.from = from;
    query.to = to;
  }
  return { preset, from, to, valid, query, interval: intervalFor(preset, from, to) };
}

const TIME_PRESETS: readonly TimePreset[] = ["LATEST_15M", "LATEST_1H", "LATEST_24H", "LATEST_7D", "CUSTOM"];

export function TimeFilterFields({ params, setParams, variant = "select" }: {
  params: URLSearchParams;
  setParams: (next: URLSearchParams) => void;
  variant?: "select" | "presets";
}) {
  const { t } = useI18n();
  const state = readTimeFilter(params);
  const labels: Record<TimePreset, string> = {
    LATEST_15M: t("filter.latest15Minutes"),
    LATEST_1H: t("filter.latestHour"),
    LATEST_24H: t("filter.latest24Hours"),
    LATEST_7D: t("filter.latest7Days"),
    CUSTOM: t("filter.customUtcRange"),
  };
  return (
    <>
      {variant === "presets" ? <div aria-label={t("filter.timeRange")} className="time-preset-list" role="group">
        {TIME_PRESETS.map((preset) => <button
          aria-pressed={state.preset === preset}
          className={state.preset === preset ? "active" : undefined}
          key={preset}
          onClick={() => setParams(updateParams(params, { timePreset: preset, ...(preset === "CUSTOM" ? {} : { from: null, to: null }) }))}
          type="button"
        >{labels[preset]}</button>)}
      </div> : <Field label={t("filter.timeRange")}>
        <select
          onChange={(event) => setParams(updateParams(params, { timePreset: event.target.value }))}
          value={state.preset}
        >
          {TIME_PRESETS.map((preset) => <option key={preset} value={preset}>{labels[preset]}</option>)}
        </select>
      </Field>}
      {state.preset === "CUSTOM" ? (
        <>
          <Field label={t("filter.from")}>
            <input
              onChange={(event) => setParams(updateParams(params, { from: event.target.value ? utcFromLocal(event.target.value) : null }))}
              type="datetime-local"
              value={state.from ? localDateTimeValue(state.from) : ""}
            />
          </Field>
          <Field label={t("filter.to")}>
            <input
              onChange={(event) => setParams(updateParams(params, { to: event.target.value ? utcFromLocal(event.target.value) : null }))}
              type="datetime-local"
              value={state.to ? localDateTimeValue(state.to) : ""}
            />
          </Field>
          {!state.valid ? <span className="field-error">{t("filter.invalidRange")}</span> : null}
        </>
      ) : null}
    </>
  );
}
