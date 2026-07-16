import type { IncidentTimeSeriesPointDto, TimeSeriesPointDto } from "../../contracts";

export interface DetectionSeriesModel {
  key: "events" | "alerts" | "incidents";
  points: readonly [number, number | null][];
}

export interface DetectionActivityModel {
  domain: readonly [number, number] | null;
  timestamps: readonly number[];
  series: readonly DetectionSeriesModel[];
}

export function buildDetectionActivityModel(
  events: readonly TimeSeriesPointDto[],
  alerts: readonly TimeSeriesPointDto[],
  incidents: readonly IncidentTimeSeriesPointDto[],
): DetectionActivityModel {
  const sourceSeries: DetectionSeriesModel[] = [
    { key: "events", points: sortPoints(events.map((row) => [Date.parse(row.bucketStartAt), row.count])) },
    { key: "alerts", points: sortPoints(alerts.map((row) => [Date.parse(row.bucketStartAt), row.count])) },
    { key: "incidents", points: sortPoints(incidents.map((row) => [Date.parse(row.bucketStartAt), row.openCount])) },
  ];
  const timestamps = [...new Set(sourceSeries.flatMap((item) => item.points.map(([timestamp]) => timestamp)))].sort((a, b) => a - b);
  const series = sourceSeries.map((item) => ({
    ...item,
    points: timestamps.map((timestamp): [number, number | null] => [timestamp, valueAt(item, timestamp) ?? null]),
  }));
  const firstTimestamp = timestamps[0];
  const lastTimestamp = timestamps.at(-1);
  return {
    domain: firstTimestamp === undefined || lastTimestamp === undefined ? null : [firstTimestamp, lastTimestamp],
    timestamps,
    series,
  };
}

export function valueAt(series: DetectionSeriesModel, timestamp: number): number | null | undefined {
  return series.points.find(([pointTimestamp]) => pointTimestamp === timestamp)?.[1];
}

function sortPoints(points: [number, number][]): [number, number][] {
  return points.filter(([timestamp]) => Number.isFinite(timestamp)).sort(([left], [right]) => left - right);
}
