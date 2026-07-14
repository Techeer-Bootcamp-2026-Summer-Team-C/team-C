import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/api/client";
import { api } from "../src/api/endpoints";
import { createDefaultOverviewLayout, type DashboardLayoutResponse } from "../src/features/dashboardLayout";
import { useDashboardLayoutEditor } from "../src/pages/OverviewPage";

const SAVED_LAYOUT: DashboardLayoutResponse = {
  dashboardKey: "overview",
  layoutVersion: 1,
  revision: 4,
  isDefault: false,
  widgets: createDefaultOverviewLayout(),
};

function EditorHarness() {
  const editor = useDashboardLayoutEditor(SAVED_LAYOUT);
  const events = editor.draft.find((item) => item.id === "kpi-events");
  return <>
    <button onClick={editor.startEditing} type="button">Start editing</button>
    <button onClick={editor.cancelEditing} type="button">Cancel editing</button>
    <button onClick={() => void editor.resetLayout()} type="button">Reset layout</button>
    <button onClick={() => editor.setHidden("kpi-events", true)} type="button">Hide events</button>
    <button onClick={() => editor.setHidden("kpi-events", false)} type="button">Show events</button>
    <span data-testid="hidden">{String(events?.hidden)}</span>
    <span data-testid="editing">{String(editor.isEditing)}</span>
    <span data-testid="status">{editor.saveStatus}</span>
    <span data-testid="conflict">{String(editor.conflict)}</span>
    <span data-testid="error">{editor.errorMessage ?? ""}</span>
  </>;
}

describe("dashboard layout save recovery", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("restores the last successful layout when a debounced save fails", async () => {
    vi.spyOn(api, "saveDashboardLayout").mockRejectedValue(new ApiError({
      status: 503,
      code: "SERVICE_UNAVAILABLE",
      message: "Layout storage is unavailable.",
      retryable: true,
      details: [],
      requestId: "req_failure",
    }));
    render(<EditorHarness />);

    fireEvent.click(screen.getByRole("button", { name: "Hide events" }));
    expect(screen.getByTestId("hidden")).toHaveTextContent("true");
    await act(async () => { await vi.advanceTimersByTimeAsync(700); });

    expect(screen.getByTestId("hidden")).toHaveTextContent("false");
    expect(screen.getByTestId("status")).toHaveTextContent("error");
    expect(screen.getByTestId("error")).toHaveTextContent("Layout storage is unavailable.");
  });

  it("surfaces revision conflicts and rolls back the optimistic change", async () => {
    vi.spyOn(api, "saveDashboardLayout").mockRejectedValue(new ApiError({
      status: 409,
      code: "DASHBOARD_LAYOUT_REVISION_CONFLICT",
      message: "Changed elsewhere.",
      retryable: false,
      details: [],
      requestId: "req_conflict",
    }));
    render(<EditorHarness />);

    fireEvent.click(screen.getByRole("button", { name: "Hide events" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(700); });

    expect(screen.getByTestId("hidden")).toHaveTextContent("false");
    expect(screen.getByTestId("status")).toHaveTextContent("conflict");
    expect(screen.getByTestId("conflict")).toHaveTextContent("true");
  });

  it("serializes rapid changes with the revision returned by the previous save", async () => {
    type SaveResponse = Awaited<ReturnType<typeof api.saveDashboardLayout>>;
    let resolveFirst!: (value: SaveResponse) => void;
    const firstSave = new Promise<SaveResponse>((resolve) => { resolveFirst = resolve; });
    const save = vi.spyOn(api, "saveDashboardLayout")
      .mockImplementationOnce(() => firstSave)
      .mockResolvedValueOnce({
        data: { ...SAVED_LAYOUT, revision: 6, widgets: createDefaultOverviewLayout() },
        meta: { requestId: "req_second" },
      });
    render(<EditorHarness />);

    fireEvent.click(screen.getByRole("button", { name: "Hide events" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(700); });
    fireEvent.click(screen.getByRole("button", { name: "Show events" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(700); });
    expect(save).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveFirst({
        data: {
          ...SAVED_LAYOUT,
          revision: 5,
          widgets: createDefaultOverviewLayout().map((item) => (
            item.id === "kpi-events" ? { ...item, hidden: true } : item
          )),
        },
        meta: { requestId: "req_first" },
      });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(save).toHaveBeenCalledTimes(2);
    expect(save.mock.calls.at(0)?.[1]?.revision).toBe(4);
    expect(save.mock.calls.at(1)?.[1]?.revision).toBe(5);
    expect(screen.getByTestId("hidden")).toHaveTextContent("false");
    expect(screen.getByTestId("status")).toHaveTextContent("saved");
  });

  it("restores and persists the edit baseline when cancel follows an automatic save", async () => {
    const hiddenWidgets = createDefaultOverviewLayout().map((item) => (
      item.id === "kpi-events" ? { ...item, hidden: true } : item
    ));
    const save = vi.spyOn(api, "saveDashboardLayout")
      .mockResolvedValueOnce({
        data: { ...SAVED_LAYOUT, revision: 5, widgets: hiddenWidgets },
        meta: { requestId: "req_hidden" },
      })
      .mockResolvedValueOnce({
        data: { ...SAVED_LAYOUT, revision: 6, widgets: createDefaultOverviewLayout() },
        meta: { requestId: "req_cancel" },
      });
    render(<EditorHarness />);

    fireEvent.click(screen.getByRole("button", { name: "Start editing" }));
    fireEvent.click(screen.getByRole("button", { name: "Hide events" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(700); });
    expect(screen.getByTestId("hidden")).toHaveTextContent("true");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Cancel editing" }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(save).toHaveBeenCalledTimes(2);
    expect(save.mock.calls.at(1)?.[1]?.revision).toBe(5);
    expect(screen.getByTestId("hidden")).toHaveTextContent("false");
    expect(screen.getByTestId("editing")).toHaveTextContent("false");
  });

  it("cancels a pending debounced save when resetting to the server default", async () => {
    const save = vi.spyOn(api, "saveDashboardLayout");
    const reset = vi.spyOn(api, "resetDashboardLayout").mockResolvedValue({
      data: { ...SAVED_LAYOUT, revision: 0, isDefault: true, widgets: createDefaultOverviewLayout() },
      meta: { requestId: "req_reset" },
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<EditorHarness />);

    fireEvent.click(screen.getByRole("button", { name: "Start editing" }));
    fireEvent.click(screen.getByRole("button", { name: "Hide events" }));
    expect(screen.getByTestId("hidden")).toHaveTextContent("true");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Reset layout" }));
      await Promise.resolve();
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(700);
    });

    expect(reset).toHaveBeenCalledTimes(1);
    expect(save).not.toHaveBeenCalled();
    expect(screen.getByTestId("hidden")).toHaveTextContent("false");
    expect(screen.getByTestId("status")).toHaveTextContent("saved");
  });

  it("clears a revision conflict after resetting to the server default", async () => {
    vi.spyOn(api, "saveDashboardLayout").mockRejectedValue(new ApiError({
      status: 409,
      code: "DASHBOARD_LAYOUT_REVISION_CONFLICT",
      message: "Changed elsewhere.",
      retryable: false,
      details: [],
      requestId: "req_conflict_before_reset",
    }));
    vi.spyOn(api, "resetDashboardLayout").mockResolvedValue({
      data: { ...SAVED_LAYOUT, revision: 0, isDefault: true, widgets: createDefaultOverviewLayout() },
      meta: { requestId: "req_reset_after_conflict" },
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<EditorHarness />);

    fireEvent.click(screen.getByRole("button", { name: "Hide events" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(700); });
    expect(screen.getByTestId("conflict")).toHaveTextContent("true");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Reset layout" }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByTestId("conflict")).toHaveTextContent("false");
    expect(screen.getByTestId("status")).toHaveTextContent("saved");
  });
});
