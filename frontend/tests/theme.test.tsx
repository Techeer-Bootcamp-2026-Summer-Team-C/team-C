import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { ThemeProvider, useTheme } from "../src/theme/ThemeProvider";

beforeEach(() => {
  document.head.innerHTML = '<meta name="color-scheme" content="dark"><meta name="theme-color" content="#09090b">';
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  document.documentElement.classList.remove("light");
  document.documentElement.style.colorScheme = "";
  vi.restoreAllMocks();
});

describe("theme lifecycle", () => {
  it("defaults missing or invalid storage to dark and restores light", () => {
    localStorage.setItem("edr.theme", "invalid");
    const { unmount } = render(<ThemeProvider><ThemeProbe /></ThemeProvider>);
    expect(screen.getByText("dark")).toBeInTheDocument();
    expect(document.documentElement).not.toHaveClass("light");
    unmount();

    localStorage.setItem("edr.theme", "light");
    render(<ThemeProvider><ThemeProbe /></ThemeProvider>);
    expect(screen.getByText("light")).toBeInTheDocument();
    expect(document.documentElement).toHaveClass("light");
  });

  it("synchronizes storage, html class, color-scheme, and theme-color", async () => {
    render(<ThemeProvider><ThemeProbe /></ThemeProvider>);
    await userEvent.click(screen.getByRole("button", { name: "toggle" }));
    expect(localStorage.getItem("edr.theme")).toBe("light");
    expect(document.documentElement).toHaveClass("light");
    expect(document.documentElement.style.colorScheme).toBe("light");
    expect(document.querySelector('meta[name="color-scheme"]')).toHaveAttribute("content", "light");
    expect(document.querySelector('meta[name="theme-color"]')).toHaveAttribute("content", "#f4f6f8");
  });

  it("keeps the app usable when theme storage throws", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    render(<ThemeProvider><ThemeProbe /></ThemeProvider>);
    expect(screen.getByText("dark")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "toggle" }));
    expect(screen.getByText("light")).toBeInTheDocument();
  });

  it("keeps the bootstrap key, dark default, light class, and meta colors aligned with the Provider", () => {
    const favicon = readFileSync("public/favicon.svg", "utf8");
    const html = readFileSync("index.html", "utf8");
    const tokens = readFileSync("src/styles/tokens.css", "utf8");
    expect(html).toContain("<title>OWLBY</title>");
    expect(favicon).toContain('class="evidence-ring"');
    expect(favicon).toContain('class="evidence-aperture"');
    expect(favicon).toContain('class="evidence-focus"');
    expect(favicon).toContain('fill-rule="evenodd"');
    expect(favicon).not.toContain("M16 5 25 9v6");
    expect(html).toContain('const key = "edr.theme"');
    expect(html).toContain('let theme = "dark"');
    expect(html).toContain('root.classList.toggle("light", theme === "light")');
    expect(html).toContain('theme === "light" ? "#f4f6f8" : "#09090b"');
    expect(tokens).toContain(":root.light");
    for (const token of ["--surface-canvas", "--surface-shell", "--surface-panel", "--text-primary", "--border-default", "--accent-primary", "--chart-events"]) {
      expect(tokens.match(new RegExp(`${token}:`, "g"))).toHaveLength(2);
    }
  });
});

function ThemeProbe() {
  const { theme, toggleTheme } = useTheme();
  return <><span>{theme}</span><button onClick={toggleTheme} type="button">toggle</button></>;
}
