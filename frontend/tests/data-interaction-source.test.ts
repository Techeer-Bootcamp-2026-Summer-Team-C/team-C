// @vitest-environment node
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("WP-03 list page adoption", () => {
  it("keeps all five target lists on the shared filter, query feedback, table, and pagination contract", () => {
    for (const page of ["AlertsPage.tsx", "IncidentsPage.tsx", "EndpointsPage.tsx", "EventsPage.tsx", "ArchivesPage.tsx"]) {
      const source = readFileSync(resolve("src/pages", page), "utf8");
      expect(source, page).toContain("FilterBar");
      expect(source, page).toContain("QueryFeedback");
      expect(source, page).toContain("DataTable");
      expect(source, page).toContain("Pagination");
      expect(source, page).not.toContain("GlobalFilterBar");
      expect(source, page).not.toContain("window.location");
    }
  });
});
