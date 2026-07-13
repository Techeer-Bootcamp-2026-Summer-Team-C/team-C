import { describe, expect, it } from "vitest";
import { parseEndpointIds } from "../src/lib/endpointIds";

describe("Endpoint ID multi-filter", () => {
  it("keeps unique positive integers in input order", () => {
    expect(parseEndpointIds("7, 2, 7, 0, nope, 11")).toEqual([7, 2, 11]);
  });

  it("returns an empty list for an empty filter", () => {
    expect(parseEndpointIds(null)).toEqual([]);
  });
});
