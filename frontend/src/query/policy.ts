import type { Query } from "@tanstack/react-query";
import type { SuccessEnvelope, UserRole } from "../contracts";
import { ApiError } from "../api/client";

export const RETRY_DELAYS_MS = [5_000, 15_000, 30_000] as const;

export function shouldRetry(failureCount: number, error: unknown): boolean {
  return error instanceof ApiError && error.status === 503 && failureCount < 3;
}

export function retryDelay(attemptIndex: number): number {
  return RETRY_DELAYS_MS[Math.min(attemptIndex, RETRY_DELAYS_MS.length - 1)] ?? 30_000;
}

export function pollingInterval(milliseconds: number): () => number | false {
  return () => (document.visibilityState === "hidden" ? false : milliseconds);
}

export function archivePollingInterval(
  query: Query<SuccessEnvelope<import("../contracts").PagedData<import("../contracts").ArchiveBucketDto>>>,
): number | false {
  if (document.visibilityState === "hidden") return false;
  const items = query.state.data?.data.items ?? [];
  return items.some((item) => item.storageStatus === "RESTORE_REQUESTED") ? 10_000 : 30_000;
}

export function canMutate(role: UserRole): boolean {
  return role === "ADMIN" || role === "ANALYST";
}
