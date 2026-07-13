export function parseEndpointIds(value: string | null): number[] {
  if (!value?.trim()) return [];
  return [...new Set(value.split(",").map((part) => Number(part.trim())).filter((item) => Number.isInteger(item) && item > 0))].slice(0, 100);
}
