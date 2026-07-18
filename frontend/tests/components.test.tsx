import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it } from "vitest";
import { ApiError } from "../src/api/client";
import { AuthProvider } from "../src/auth/AuthContext";
import { EmptyState, ErrorState, ResponseGuidance, Skeleton, StaleWarning, StatusPill } from "../src/components/ui";
import { LocaleProvider } from "../src/i18n/LocaleContext";

afterEach(cleanup);

it("renders loading, empty, null/error, stale, and text-labelled status states", () => {
  const error = new ApiError({ status: 503, code: "SERVICE_UNAVAILABLE", message: "Backend unavailable", retryable: true, details: [], requestId: "req_state" });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><AuthProvider><LocaleProvider><MemoryRouter><Skeleton rows={2} /><EmptyState title="No rows" message="The result array is empty." /><ErrorState error={error} /><StaleWarning error={error} onRetry={() => undefined} /><StatusPill value="CRITICAL" /></MemoryRouter></LocaleProvider></AuthProvider></QueryClientProvider>);
  expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
  expect(screen.getByText("No rows")).toBeInTheDocument();
  expect(screen.getAllByText(/req_state/i)).toHaveLength(2);
  expect(screen.getByText("Critical")).toBeInTheDocument();
});

it("renders ordered read-only response guidance with explicit manual action labels", () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><AuthProvider><LocaleProvider><MemoryRouter><ResponseGuidance steps={[
    { order: 1, title: "Preserve evidence", description: "Capture the process tree.", requiresManualAction: true },
    { order: 2, title: "Review scope", description: "Review related alerts.", requiresManualAction: false },
  ]} /></MemoryRouter></LocaleProvider></AuthProvider></QueryClientProvider>);
  const list = screen.getByRole("list", { name: "Ordered response guidance steps" });
  expect(within(list).getAllByRole("listitem")).toHaveLength(2);
  expect(within(list).getByText("Manual action")).toBeInTheDocument();
  expect(within(list).queryByRole("checkbox")).not.toBeInTheDocument();
  expect(within(list).queryByRole("button")).not.toBeInTheDocument();
});

it("renders a compact empty state with an explicit recovery action", () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><AuthProvider><LocaleProvider><MemoryRouter><EmptyState actions={<button type="button">View 7 days</button>} compact message="Widen the current time range." title="No activity" /></MemoryRouter></LocaleProvider></AuthProvider></QueryClientProvider>);
  expect(screen.getByText("No activity").closest(".state-card")).toHaveClass("compact");
  expect(screen.getByRole("button", { name: "View 7 days" })).toBeInTheDocument();
});

it("renders the explicit empty state when a RuleV1 version has no guidance", () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><AuthProvider><LocaleProvider><MemoryRouter><ResponseGuidance steps={[]} /></MemoryRouter></LocaleProvider></AuthProvider></QueryClientProvider>);
  expect(screen.getByText("No response guidance")).toBeInTheDocument();
});
