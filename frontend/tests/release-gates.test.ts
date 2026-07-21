// @vitest-environment node
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const ROUTE_PAGES = [
  "AlertDetailPage",
  "AlertsPage",
  "ArchivesPage",
  "EndpointDetailPage",
  "EndpointsPage",
  "EventDetailPage",
  "EventsPage",
  "IncidentDetailPage",
  "IncidentsPage",
  "IntelligencePage",
  "OperationsPage",
  "OverviewPage",
] as const;

describe("WP-09 release gates", () => {
  it("loads authenticated pages by route while keeping Login critical", () => {
    const source = readFileSync(resolve("src/App.tsx"), "utf8");

    expect(source).toContain('import { LoginPage } from "./pages/LoginPage"');
    for (const page of ROUTE_PAGES) {
      expect(source, page).toContain(`import("./pages/${page}")`);
      expect(source, page).not.toContain(`import { ${page} } from "./pages/${page}"`);
    }
  });

  it("keeps an accessible route loading boundary and reduced-motion fallback", () => {
    const shell = readFileSync(resolve("src/components/AppShell.tsx"), "utf8");
    const styles = readFileSync(resolve("src/styles/shell.css"), "utf8");

    expect(shell).toContain("<Suspense");
    expect(shell).toContain('className="route-loading"');
    expect(shell).toContain('role="status"');
    expect(styles).toContain("prefers-reduced-motion: reduce");
  });

  it("keeps vertical page scrolling on the browser document", () => {
    for (const file of ["src/styles.css", "src/styles/shell.css"]) {
      const source = readFileSync(resolve(file), "utf8");
      const consoleRules = [...source.matchAll(/\.console-shell\s*\{([^}]*)\}/g)].map(
        (match) => match[1] ?? "",
      );
      const mainRule = source.match(/\.main-content\s*\{([^}]*)\}/)?.[1] ?? "";

      expect(consoleRules.length, file).toBeGreaterThan(0);
      expect(consoleRules[0], file).toContain("min-height: 100dvh");
      expect(consoleRules[0], file).toMatch(/grid-template-rows:[^;]*auto/);
      expect(
        consoleRules.every((rule) => !/(?:^|;)\s*height:\s*100dvh/.test(rule)),
        file,
      ).toBe(true);
      expect(mainRule, file).toContain("overflow: visible");
      expect(source, file).toMatch(/\.top-bar\s*\{[^}]*position:\s*sticky/);
    }
  });

  it("documents both graph flags with enabled release defaults", () => {
    for (const file of ["../.env.example", "../.env.production.example"]) {
      const source = readFileSync(resolve(file), "utf8");
      expect(source, file).toContain("VITE_INCIDENT_GRAPH_ENABLED=true");
      expect(source, file).toContain("VITE_TOPOLOGY_GRAPH_ENABLED=true");
    }
  });

  it("excludes user and raw payload controls from print while exposing table fallbacks", () => {
    const legacy = readFileSync(resolve("src/styles.css"), "utf8");
    const eventStyles = readFileSync(resolve("src/styles/pages/endpoints-events.css"), "utf8");
    const patterns = readFileSync(resolve("src/styles/patterns.css"), "utf8");

    expect(legacy).toContain(".top-bar");
    expect(eventStyles).toContain(".raw-payload-panel { display: none !important; }");
    expect(patterns).toContain(".chart-frame-fallback:not([open]) > :not(summary)");
    expect(patterns).toContain(".table-fallback:not([open]) > :not(summary)");
  });
});
