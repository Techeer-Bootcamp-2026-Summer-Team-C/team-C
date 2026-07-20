// @vitest-environment node
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SOURCE = resolve("src");

describe("Frontend responsibility boundaries", () => {
  it("keeps fetch inside src/api and browser storage within approved auth and layout boundaries", () => {
    for (const file of sourceFiles(SOURCE)) {
      const content = readFileSync(file, "utf8");
      const name = relative(SOURCE, file).replace(/\\/g, "/");
      if (/\bfetch\s*\(/.test(content)) expect(name).toBe("api/client.ts");
      if (content.includes("localStorage")) {
        expect(["components/AppShell.tsx", "theme/ThemeProvider.tsx", "features/overviewLayout/overviewLayoutStorage.ts"]).toContain(name);
        if (name === "components/AppShell.tsx") expect(content).toContain("edr.compactNavigation");
        if (name === "theme/ThemeProvider.tsx") expect(content).toContain("edr.theme");
        if (name === "features/overviewLayout/overviewLayoutStorage.ts") {
          expect(content).toContain("edr.overviewDashboards.v1.user.");
          expect(content).toContain("edr.overviewActiveDashboard.v1.user.");
        }
        expect(content).not.toMatch(/token|accessToken|lastPrimaryRoute/);
      }
      if (content.includes("sessionStorage")) {
        expect(name).toBe("auth/AuthContext.tsx");
        expect(content).toContain("edr.authSession");
      }
    }
  });

  it("does not aggregate raw Alert, Event, Risk factor, or chart bucket rows", () => {
    for (const file of sourceFiles(SOURCE)) {
      const content = readFileSync(file, "utf8");
      expect(content).not.toMatch(/(?:alerts|events|riskFactors)\.reduce\s*\(/);
      expect(content).not.toMatch(/build(?:Alert|Event|Risk|Time).*Bucket/i);
    }
  });

  it("keeps screen refresh user-triggered throughout the app", () => {
    for (const file of sourceFiles(SOURCE)) {
      const content = readFileSync(file, "utf8");
      expect(content).not.toContain("refetchInterval:");
      expect(content).not.toMatch(/(?:window\.)?location\.(?:reload|href\s*=)/);
      expect(content).not.toMatch(/\b(?:WebSocket|EventSource)\b/);
      expect(content).not.toContain("serviceWorker");
      expect(content).not.toContain("setInterval(");
    }

    const main = readFileSync(resolve("src/main.tsx"), "utf8");
    expect(main).toContain("retry: false");
    expect(main).toContain("retryOnMount: false");
    expect(main).toContain("refetchOnMount: false");
    expect(main).toContain("refetchOnWindowFocus: false");
    expect(main).toContain("refetchOnReconnect: false");
    expect(main).toContain('networkMode: "always"');

    const viteConfig = readFileSync(resolve("vite.config.ts"), "utf8");
    expect(viteConfig).toContain("hmr: false");

    const overview = readFileSync(resolve("src/pages/OverviewPage.tsx"), "utf8");
    expect(overview).not.toContain("overview.autoRefresh");
    expect(overview).toContain("onRefresh={refreshManually}");
  });
});

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(ts|tsx)$/.test(entry) ? [path] : [];
  });
}
