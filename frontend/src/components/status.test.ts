import { describe, expect, it } from "vitest";
import { POLL_MAX_MS, POLL_START_MS, isUnresolved, nextPollDelay, statusLabel } from "./status";

describe("status polling", () => {
  it("backs off from 2 s to a 10 s cap", () => {
    const seen = [POLL_START_MS];
    for (let i = 0; i < 6; i++) seen.push(nextPollDelay(seen[seen.length - 1]!));
    expect(seen).toEqual([2000, 3000, 4500, 6750, 10000, 10000, 10000]);
    expect(Math.max(...seen)).toBe(POLL_MAX_MS);
  });
  it("keeps polling only while a status can still change", () => {
    expect(isUnresolved("INDEXING")).toBe(true);
    expect(isUnresolved("READY")).toBe(false);
    expect(isUnresolved("FAILED")).toBe(false);
  });
  it("shows readable labels", () => {
    expect(statusLabel("INDEXING")).toBe("Indexing…");
    expect(statusLabel("READY")).toBe("Ready");
  });
});
