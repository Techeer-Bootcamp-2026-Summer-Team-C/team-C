import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { Button, Dialog, Drawer, Popover, TextField, Tooltip } from "../src/components/primitives";

afterEach(() => cleanup());

describe("shared primitive contracts", () => {
  it("exposes loading, validation, and tooltip state to assistive technology", async () => {
    render(<>
      <Button loading>Save changes</Button>
      <TextField error="Login ID is required" label="Login ID" />
      <Tooltip label="Compact navigation"><button type="button">Compact</button></Tooltip>
    </>);

    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save changes" })).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("textbox", { name: "Login ID" })).toHaveAccessibleDescription("Login ID is required");
    expect(screen.getByRole("textbox", { name: "Login ID" })).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "Compact" })).toHaveAccessibleDescription("Compact navigation");
  });

  it("closes a popover with Escape and restores focus to its trigger", async () => {
    const user = userEvent.setup();
    render(<Popover label="Account menu" trigger={<span>AU</span>}><p>Account details</p></Popover>);
    const trigger = screen.getByRole("button", { name: "Account menu" });
    await user.click(trigger);
    expect(screen.getByRole("dialog", { name: "Account menu" })).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Account menu" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("traps modal focus, closes with Escape, and returns focus for Dialog and Drawer", async () => {
    const user = userEvent.setup();
    render(<ModalHarness />);

    const dialogTrigger = screen.getByRole("button", { name: "Open dialog" });
    await user.click(dialogTrigger);
    const dialog = screen.getByRole("dialog", { name: "Evidence export" });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close dialog" })).toHaveFocus();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(dialogTrigger).toHaveFocus());

    const drawerTrigger = screen.getByRole("button", { name: "Open drawer" });
    await user.click(drawerTrigger);
    expect(screen.getByRole("dialog", { name: "Primary navigation" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close drawer" })).toHaveFocus();
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(screen.getByRole("link", { name: "Overview" })).toHaveFocus();
    await user.keyboard("{Tab}");
    expect(screen.getByRole("button", { name: "Close drawer" })).toHaveFocus();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(drawerTrigger).toHaveFocus());
  });
});

function ModalHarness() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerTriggerRef = useRef<HTMLButtonElement>(null);
  return <>
    <button onClick={() => setDialogOpen(true)} type="button">Open dialog</button>
    <Dialog closeLabel="Close dialog" onClose={() => setDialogOpen(false)} open={dialogOpen} title="Evidence export">
      <button type="button">Download</button>
    </Dialog>
    <button onClick={() => setDrawerOpen(true)} ref={drawerTriggerRef} type="button">Open drawer</button>
    <Drawer closeLabel="Close drawer" label="Primary navigation" onClose={() => setDrawerOpen(false)} open={drawerOpen} returnFocusRef={drawerTriggerRef}>
      <a href="/">Overview</a>
    </Drawer>
  </>;
}
