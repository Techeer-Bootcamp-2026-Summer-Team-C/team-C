import { LineChart } from "echarts/charts";
import { AxisPointerComponent, GridComponent, TooltipComponent } from "echarts/components";
import { init, use as registerECharts, type EChartsType } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { IncidentTimeSeriesPointDto, TimeSeriesPointDto } from "../../contracts";
import { useI18n } from "../../i18n/LocaleContext";
import { formatCompactDate } from "../../lib/format";
import { EmptyState } from "../../components/ui";
import { useTheme } from "../../theme/ThemeProvider";
import { buildDetectionActivityModel, valueAt } from "./overviewChartModel";

registerECharts([LineChart, GridComponent, TooltipComponent, AxisPointerComponent, CanvasRenderer]);

export default function DetectionActivityPanel({ events, alerts, incidents, recoveryTo }: {
  events: TimeSeriesPointDto[];
  alerts: TimeSeriesPointDto[];
  incidents: IncidentTimeSeriesPointDto[];
  recoveryTo?: string;
}) {
  const { t } = useI18n();
  const { theme } = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<EChartsType | null>(null);
  const renderedRef = useRef(false);
  const [selectedTimestamp, setSelectedTimestamp] = useState<number | null>(null);
  const model = useMemo(() => buildDetectionActivityModel(events, alerts, incidents), [alerts, events, incidents]);
  const hasDomain = model.domain !== null;
  const labels = useMemo(() => [t("overview.events"), t("overview.alerts"), t("overview.openIncidents")], [t]);

  useEffect(() => {
    setSelectedTimestamp((current) => current !== null && !model.timestamps.includes(current) ? null : current);
  }, [model.timestamps]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !hasDomain) return;
    const chart = init(container, undefined, { renderer: "canvas" });
    chartRef.current = chart;
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => chart.resize());
    observer?.observe(container);
    const resizeForPrint = () => chart.resize();
    window.addEventListener("resize", resizeForPrint);
    window.addEventListener("beforeprint", resizeForPrint);
    window.addEventListener("afterprint", resizeForPrint);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", resizeForPrint);
      window.removeEventListener("beforeprint", resizeForPrint);
      window.removeEventListener("afterprint", resizeForPrint);
      chart.dispose();
      chartRef.current = null;
    };
  }, [hasDomain]);

  useEffect(() => {
    const chart = chartRef.current;
    const container = containerRef.current;
    if (!chart || !container || !model.domain) return;
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const animate = !renderedRef.current && !reducedMotion;
    container.dataset.animation = animate ? "enabled" : "disabled";
    const styles = getComputedStyle(container);
    const color = (name: string, fallback: string) => styles.getPropertyValue(name).trim() || fallback;
    const colors = [color("--chart-events", "#2563e9"), color("--chart-alerts", "#7c83fd"), color("--chart-incidents", "#16a249")];
    const fills = [color("--chart-events-fill", "rgba(37, 99, 233, .18)"), color("--chart-alerts-fill", "rgba(124, 131, 253, .12)"), color("--chart-incidents-fill", "rgba(22, 162, 73, .1)")];
    const transparentFills = ["rgba(37, 99, 233, 0)", "rgba(124, 131, 253, 0)", "rgba(22, 162, 73, 0)"];
    const chartFont = color("--font-ui", '"Inter Variable", "Pretendard Variable", sans-serif');
    const chartMetaSize = Number.parseFloat(color("--type-meta", "11px")) || 11;
    const compactChart = container.clientHeight < 220;
    chart.setOption({
      animation: animate,
      animationDuration: 280,
      textStyle: { fontFamily: chartFont },
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      grid: [
        { left: Math.max(44, chartMetaSize * 4), right: 16, top: "4%", height: "22%" },
        { left: Math.max(44, chartMetaSize * 4), right: 16, top: "35%", height: "22%" },
        { left: Math.max(44, chartMetaSize * 4), right: 16, top: "66%", height: "22%" },
      ],
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        backgroundColor: color("--surface-raised", "#1b1b20"),
        borderColor: color("--border-default", "#5d5e67"),
        textStyle: { color: color("--text-primary", "#f5f5f6"), fontFamily: chartFont, fontSize: chartMetaSize },
        formatter: (raw: unknown) => formatTooltip(raw, labels),
      },
      xAxis: model.series.map((_series, index) => ({
        type: "time",
        gridIndex: index,
        min: model.domain?.[0],
        max: model.domain?.[1],
        axisLabel: { color: color("--chart-axis", "#8d8f98"), fontSize: chartMetaSize, hideOverlap: true, show: index === 2 },
        axisLine: { lineStyle: { color: color("--chart-grid", "#24252a") } },
        axisTick: { show: false },
        splitLine: { show: false },
      })),
      yAxis: model.series.map((_series, index) => ({
        type: "value",
        gridIndex: index,
        minInterval: 1,
        splitNumber: compactChart ? 2 : 4,
        axisLabel: { color: color("--chart-axis", "#8d8f98"), fontSize: chartMetaSize, hideOverlap: true },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: color("--chart-grid", "#24252a") } },
      })),
      series: model.series.map((series, index) => ({
        name: labels[index],
        type: "line",
        xAxisIndex: index,
        yAxisIndex: index,
        data: series.points,
        symbol: "circle",
        symbolSize: 6,
        showSymbol: series.points.length < 18,
        connectNulls: false,
        lineStyle: { color: colors[index], width: 2 },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: fills[index] },
              { offset: 1, color: transparentFills[index] },
            ],
          },
        },
        itemStyle: { color: colors[index] },
        emphasis: { focus: "series" },
      })),
    });
    renderedRef.current = true;
  }, [labels, model, theme]);

  if (!model.domain) return <EmptyState actions={recoveryTo ? <Link className="button" to={recoveryTo}>{t("filter.latest7Days")}</Link> : undefined} compact title={t("charts.noDetectionActivity")} message={t("charts.noSeriesDescription")} />;

  const latest = model.series.map((series) => series.points.at(-1)?.[1]);
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  return <div className="detection-activity-echarts">
    <p className="sr-only">{t("charts.detectionSummary", { events: latest[0] ?? t("common.none"), alerts: latest[1] ?? t("common.none"), incidents: latest[2] ?? t("common.none") })}</p>
    <ul aria-label={t("charts.currentValues")} className="activity-current-values">
      {labels.map((label, index) => <li className={`series-${["events", "alerts", "incidents"][index]}`} key={label}><span><i aria-hidden="true" />{label}</span><strong>{latest[index] ?? t("common.none")}</strong></li>)}
    </ul>
    <p className="activity-time-context">{t("charts.timeContext", {
      from: formatCompactDate(new Date(model.domain[0]).toISOString()),
      to: formatCompactDate(new Date(model.domain[1]).toISOString()),
      timezone,
    })}</p>
    <div aria-hidden="true" className="detection-echarts-canvas" ref={containerRef} />
    <label className="activity-bucket-inspector"><span>{t("charts.bucketSelection")}</span><select
      aria-label={t("charts.bucketSelection")}
      onChange={(event) => {
        const timestamp = Number(event.target.value);
        if (Number.isFinite(timestamp) && event.target.value) selectTimestamp(timestamp);
        else setSelectedTimestamp(null);
      }}
      value={selectedTimestamp ?? ""}
    ><option value="">{t("charts.selectBucket")}</option>{model.timestamps.map((timestamp) => <option key={timestamp} value={timestamp}>{formatCompactDate(new Date(timestamp).toISOString())}</option>)}</select></label>
    {selectedTimestamp === null ? null : <p aria-live="polite" className="chart-selected-value">{selectionSummary(selectedTimestamp)}</p>}
  </div>;

  function selectTimestamp(timestamp: number) {
    setSelectedTimestamp(timestamp);
    const seriesIndex = model.series.findIndex((series) => typeof valueAt(series, timestamp) === "number");
    const selectedSeries = model.series[seriesIndex];
    const dataIndex = selectedSeries ? selectedSeries.points.findIndex(([pointTimestamp]) => pointTimestamp === timestamp) : -1;
    if (seriesIndex >= 0 && dataIndex >= 0) chartRef.current?.dispatchAction({ type: "showTip", seriesIndex, dataIndex });
  }

  function selectionSummary(timestamp: number): string {
    const values = model.series.map((series, index) => {
      const value = valueAt(series, timestamp);
      return `${labels[index]} ${value ?? t("common.none")}`;
    });
    return `${formatCompactDate(new Date(timestamp).toISOString())}: ${values.join(", ")}`;
  }
}

function formatTooltip(raw: unknown, labels: string[]): string {
  const params = Array.isArray(raw) ? raw : [raw];
  const rows = params.filter(isTooltipParam);
  if (!rows.length) return "";
  const firstRow = rows[0];
  const timestamp = firstRow && Array.isArray(firstRow.value) ? Number(firstRow.value[0]) : Number.NaN;
  return [`<strong>${Number.isFinite(timestamp) ? formatCompactDate(new Date(timestamp).toISOString()) : ""}</strong>`, ...rows.map((row) => {
    const value = Array.isArray(row.value) ? row.value[1] : row.value;
    return `${labels[row.seriesIndex] ?? row.seriesName}: ${String(value)}`;
  })].join("<br>");
}

function isTooltipParam(value: unknown): value is { value: unknown; seriesIndex: number; seriesName: string } {
  return typeof value === "object" && value !== null && "value" in value && "seriesIndex" in value && "seriesName" in value;
}
