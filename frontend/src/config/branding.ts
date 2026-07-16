const FALLBACK_SERVICE_NAME = "EDR Console";
const configuredServiceName = (import.meta.env.VITE_SERVICE_NAME as string | undefined)?.trim();

export const SERVICE_NAME: string = configuredServiceName || FALLBACK_SERVICE_NAME;

export const SERVICE_MARK = SERVICE_NAME
  .split(/\s+/)
  .filter(Boolean)
  .slice(0, 2)
  .map((word) => word[0]?.toUpperCase() ?? "")
  .join("") || "EC";
