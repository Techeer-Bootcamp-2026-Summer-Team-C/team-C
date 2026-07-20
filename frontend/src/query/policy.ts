import type { UserRole } from "../contracts";

export function canMutate(role: UserRole): boolean {
  return role === "ADMIN" || role === "ANALYST";
}
