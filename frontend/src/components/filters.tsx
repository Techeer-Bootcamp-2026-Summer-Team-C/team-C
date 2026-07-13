import type { DashboardTimeQuery, TimePreset } from "../contracts";
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
  const preset = timePreset(params);
  const from = params.get("from") ?? undefined;
  const to = params.get("to") ?? undefined;
  const valid = preset !== "CUSTOM" || Boolean(from && to && Date.parse(from) < Date.parse(to));
  const query: DashboardTimeQuery = { timePreset: preset };
  if (preset === "CUSTOM" && from && to) {
    query.from = from;
    query.to = to;
  }
  return { preset, from, to, valid, query, interval: intervalFor(preset, from, to) };
}

export function TimeFilterFields({ params, setParams }: {
  params: URLSearchParams;
  setParams: (next: URLSearchParams) => void;
}) {
  const state = readTimeFilter(params);
  return (
    <>
      <Field label="Time range">
        <select
          onChange={(event) => setParams(updateParams(params, { timePreset: event.target.value }))}
          value={state.preset}
        >
          <option value="LATEST_15M">Latest 15 minutes</option>
          <option value="LATEST_1H">Latest hour</option>
          <option value="LATEST_24H">Latest 24 hours</option>
          <option value="LATEST_7D">Latest 7 days</option>
          <option value="CUSTOM">Custom UTC range</option>
        </select>
      </Field>
      {state.preset === "CUSTOM" ? (
        <>
          <Field label="From">
            <input
              onChange={(event) => setParams(updateParams(params, { from: event.target.value ? utcFromLocal(event.target.value) : null }))}
              type="datetime-local"
              value={state.from ? localDateTimeValue(state.from) : ""}
            />
          </Field>
          <Field label="To">
            <input
              onChange={(event) => setParams(updateParams(params, { to: event.target.value ? utcFromLocal(event.target.value) : null }))}
              type="datetime-local"
              value={state.to ? localDateTimeValue(state.to) : ""}
            />
          </Field>
          {!state.valid ? <span className="field-error">From and to are required, and from must be earlier than to.</span> : null}
        </>
      ) : null}
    </>
  );
}
