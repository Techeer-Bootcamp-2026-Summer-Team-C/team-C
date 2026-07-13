import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";
import { ApiError } from "../src/api/client";
import { EmptyState, ErrorState, Skeleton, StaleWarning, StatusPill } from "../src/components/ui";

it("renders loading, empty, null/error, stale, and text-labelled status states", () => {
  const error = new ApiError({ status: 503, code: "SERVICE_UNAVAILABLE", message: "Backend unavailable", retryable: true, details: [], requestId: "req_state" });
  render(<MemoryRouter><Skeleton rows={2} /><EmptyState title="No rows" message="The result array is empty." /><ErrorState error={error} /><StaleWarning error={error} onRetry={() => undefined} /><StatusPill value="CRITICAL" /></MemoryRouter>);
  expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
  expect(screen.getByText("No rows")).toBeInTheDocument();
  expect(screen.getAllByText(/req_state/i)).toHaveLength(2);
  expect(screen.getByText("Critical")).toBeInTheDocument();
});
