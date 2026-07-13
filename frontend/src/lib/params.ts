export function allowedValue<const T extends readonly string[]>(
  value: string | null,
  allowed: T,
): T[number] | undefined {
  return value !== null && allowed.includes(value) ? (value as T[number]) : undefined;
}

export function positiveInteger(value: string | null): number | undefined {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}
