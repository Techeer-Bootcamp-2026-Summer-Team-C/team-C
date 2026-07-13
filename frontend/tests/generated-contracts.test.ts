import { readFileSync, readdirSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const root = resolve(import.meta.dirname, "../src");

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((name) => {
    const path = resolve(directory, name);
    if (path.includes(resolve(root, "api/generated"))) return [];
    return statSync(path).isDirectory() ? sourceFiles(path) : path.endsWith(".ts") || path.endsWith(".tsx") ? [path] : [];
  });
}

describe("generated OpenAPI contract boundary", () => {
  it("keeps generated components behind contracts.ts without manual DTO interfaces", () => {
    const contracts = readFileSync(resolve(root, "contracts.ts"), "utf8");
    expect(contracts).toContain('from "./api/generated/schema"');
    expect(contracts).not.toMatch(/^export interface /m);
    expect(contracts).toContain('Schemas["EndpointDto"]');
    expect(contracts).toContain('QueryOf<"eventsList">');
  });

  it("does not expose generated paths or components directly to screens", () => {
    const consumers = sourceFiles(root).filter((path) => !path.endsWith("contracts.ts"));
    for (const path of consumers) {
      expect(readFileSync(path, "utf8"), path).not.toContain("api/generated/schema");
    }
  });
});
