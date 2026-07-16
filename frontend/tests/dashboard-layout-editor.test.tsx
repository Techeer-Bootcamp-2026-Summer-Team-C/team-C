import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/api/client";
import { api } from "../src/api/endpoints";
import { createDefaultOverviewLayout, type DashboardLayoutResponse } from "../src/features/dashboardLayout";
import { useDashboardLayoutEditor } from "../src/pages/OverviewPage";
import { dashboardLayoutV1Fixture } from "./dashboard-layout-v1.fixture";

const SAVED_LAYOUT: DashboardLayoutResponse = {
  dashboardKey: "overview",
  layoutVersion: 2,
  revision: 4,
  isDefault: false,
  widgets: createDefaultOverviewLayout(),
};

function EditorHarness() {
  const editor = useDashboardLayoutEditor(SAVED_LAYOUT);
  const events = editor.draft.find((item) => item.id === "kpi-alerts");
  return <>
    <button onClick={editor.startEditing} type="button">Start editing</button>
    <button onClick={() => void editor.finishEditing()} type="button">Finish editing</button>
    <button onClick={editor.cancelEditing} type="button">Cancel editing</button>
    <button onClick={() => void editor.resetLayout()} type="button">Reset layout</button>
    <button onClick={() => editor.setHidden("kpi-alerts", true)} type="button">Hide events</button>
    <button onClick={() => editor.setHidden("kpi-alerts", false)} type="button">Show events</button>
    <span data-testid="hidden">{String(events?.hidden)}</span>
    <span data-testid="editing">{String(editor.isEditing)}</span>
    <span data-testid="status">{editor.saveStatus}</span>
    <span data-testid="conflict">{String(editor.conflict)}</span>
    <span data-testid="error">{editor.errorMessage ?? ""}</span>
  </>;
}

function MigrationHarness({ response }: { response: DashboardLayoutResponse }) {
  const editor = useDashboardLayoutEditor(response, 7, undefined, { autoMigrate: true });
  return <>
    <button onClick={() => void editor.retryMigration()} type="button">Retry migration</button>
    <button onClick={editor.dismissMigrationNotice} type="button">Dismiss migration</button>
    <span data-testid="migration-status">{editor.migrationStatus}</span>
    <span data-testid="migration-notice">{String(editor.migrationNotice)}</span>
    <span data-testid="migration-count">{editor.draft.length}</span>
    <span data-testid="migration-detection">{String(editor.draft.some((item) => item.id === "detection-activity") && !editor.draft.some((item) => item.id === "event-volume"))}</span>
  </>;
}

describe("dashboard layout save recovery", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    window.sessionStorage.clear();
  });
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

    fireEvent.click(screen.getByRole("button", { name: "Start editing" }));
    fireEvent.click(screen.getByRole("button", { name: "Hide events" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Finish editing" }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByTestId("hidden")).toHaveTextContent("false");
    expect(screen.getByTestId("editing")).toHaveTextContent("true");
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
            item.id === "kpi-alerts" ? { ...item, hidden: true } : item
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

  it("keeps edit mode open until Done flushes the pending save", async () => {
    type SaveResponse = Awaited<ReturnType<typeof api.saveDashboardLayout>>;
    let resolveSave!: (value: SaveResponse) => void;
    const save = vi.spyOn(api, "saveDashboardLayout").mockImplementation(() => (
      new Promise<SaveResponse>((resolve) => { resolveSave = resolve; })
    ));
    render(<EditorHarness />);

    fireEvent.click(screen.getByRole("button", { name: "Start editing" }));
    fireEvent.click(screen.getByRole("button", { name: "Hide events" }));
    fireEvent.click(screen.getByRole("button", { name: "Finish editing" }));
    expect(screen.getByTestId("editing")).toHaveTextContent("true");
    expect(screen.getByTestId("status")).toHaveTextContent("saving");

    await act(async () => {
      resolveSave({
        data: {
          ...SAVED_LAYOUT,
          revision: 5,
          widgets: createDefaultOverviewLayout().map((item) => (
      item.id === "kpi-alerts" ? { ...item, hidden: true } : item
          )),
        },
        meta: { requestId: "req_finish" },
      });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(save).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("editing")).toHaveTextContent("false");
    expect(screen.getByTestId("hidden")).toHaveTextContent("true");
    expect(screen.getByTestId("status")).toHaveTextContent("saved");
  });

  it("waits for an in-flight save and its latest queued draft before finishing", async () => {
    type SaveResponse = Awaited<ReturnType<typeof api.saveDashboardLayout>>;
    let resolveFirst!: (value: SaveResponse) => void;
    const firstSave = new Promise<SaveResponse>((resolve) => { resolveFirst = resolve; });
    const save = vi.spyOn(api, "saveDashboardLayout")
      .mockImplementationOnce(() => firstSave)
      .mockResolvedValueOnce({
        data: { ...SAVED_LAYOUT, revision: 6, widgets: createDefaultOverviewLayout() },
        meta: { requestId: "req_finish_second" },
      });
    render(<EditorHarness />);

    fireEvent.click(screen.getByRole("button", { name: "Start editing" }));
    fireEvent.click(screen.getByRole("button", { name: "Hide events" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(700); });
    fireEvent.click(screen.getByRole("button", { name: "Show events" }));
    fireEvent.click(screen.getByRole("button", { name: "Finish editing" }));
    expect(screen.getByTestId("editing")).toHaveTextContent("true");
    expect(save).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveFirst({
        data: {
          ...SAVED_LAYOUT,
          revision: 5,
          widgets: createDefaultOverviewLayout().map((item) => (
            item.id === "kpi-alerts" ? { ...item, hidden: true } : item
          )),
        },
        meta: { requestId: "req_finish_first" },
      });
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(save).toHaveBeenCalledTimes(2);
    expect(save.mock.calls.at(0)?.[1]?.revision).toBe(4);
    expect(save.mock.calls.at(1)?.[1]?.revision).toBe(5);
    expect(screen.getByTestId("editing")).toHaveTextContent("false");
    expect(screen.getByTestId("hidden")).toHaveTextContent("false");
  });

  it("keeps edit mode open when the Done save fails", async () => {
    vi.spyOn(api, "saveDashboardLayout").mockRejectedValue(new ApiError({
      status: 503,
      code: "SERVICE_UNAVAILABLE",
      message: "Layout storage is unavailable.",
      retryable: true,
      details: [],
      requestId: "req_finish_failure",
    }));
    render(<EditorHarness />);

    fireEvent.click(screen.getByRole("button", { name: "Start editing" }));
    fireEvent.click(screen.getByRole("button", { name: "Hide events" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Finish editing" }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByTestId("editing")).toHaveTextContent("true");
    expect(screen.getByTestId("hidden")).toHaveTextContent("false");
    expect(screen.getByTestId("status")).toHaveTextContent("error");
  });

  it("warns before browser unload while a layout save is pending", () => {
    vi.spyOn(api, "saveDashboardLayout").mockResolvedValue({
      data: { ...SAVED_LAYOUT, revision: 5 },
      meta: { requestId: "req_beforeunload" },
    });
    render(<EditorHarness />);

    fireEvent.click(screen.getByRole("button", { name: "Hide events" }));
    const event = new Event("beforeunload", { cancelable: true });

    expect(window.dispatchEvent(event)).toBe(false);
    expect(event.defaultPrevented).toBe(true);
  });

  it("restores and persists the edit baseline when cancel follows an automatic save", async () => {
    const hiddenWidgets = createDefaultOverviewLayout().map((item) => (
            item.id === "kpi-alerts" ? { ...item, hidden: true } : item
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

  it("automatically persists a v1 layout as the approved v2 registry and shows a post-save notice", async () => {
    const save = vi.spyOn(api, "saveDashboardLayout").mockResolvedValue({
      data: { ...SAVED_LAYOUT, revision: 8, widgets: createDefaultOverviewLayout() },
      meta: { requestId: "req_migration" },
    });
    const response = { ...dashboardLayoutV1Fixture.data, widgets: [...dashboardLayoutV1Fixture.data.widgets] };
    render(<StrictMode><MigrationHarness response={response} /></StrictMode>);

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0]?.[1]).toMatchObject({ layoutVersion: 2, revision: 7 });
    expect(save.mock.calls[0]?.[1]?.widgets).toHaveLength(10);
    expect(screen.getByTestId("migration-count")).toHaveTextContent("10");
    expect(screen.getByTestId("migration-detection")).toHaveTextContent("true");
    expect(screen.getByTestId("migration-status")).toHaveTextContent("complete");
    expect(screen.getByTestId("migration-notice")).toHaveTextContent("true");
    fireEvent.click(screen.getByRole("button", { name: "Dismiss migration" }));
    expect(screen.getByTestId("migration-notice")).toHaveTextContent("false");
  });

  it("keeps a failed v1 migration retryable", async () => {
    const save = vi.spyOn(api, "saveDashboardLayout")
      .mockRejectedValueOnce(new ApiError({
        status: 503,
        code: "SERVICE_UNAVAILABLE",
        message: "Layout storage is unavailable.",
        retryable: true,
        details: [],
        requestId: "req_migration_failure",
      }))
      .mockResolvedValueOnce({
        data: { ...SAVED_LAYOUT, revision: 8, widgets: createDefaultOverviewLayout() },
        meta: { requestId: "req_migration_retry" },
      });
    const response = { ...dashboardLayoutV1Fixture.data, widgets: [...dashboardLayoutV1Fixture.data.widgets] };
    render(<MigrationHarness response={response} />);

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByTestId("migration-status")).toHaveTextContent("failed");
    expect(screen.getByTestId("migration-notice")).toHaveTextContent("false");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Retry migration" }));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(save).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId("migration-status")).toHaveTextContent("complete");
    expect(screen.getByTestId("migration-notice")).toHaveTextContent("true");
  });
});
