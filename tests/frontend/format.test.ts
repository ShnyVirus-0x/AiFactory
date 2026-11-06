import { describe, expect, it } from "vitest";
import { fmtBytes, fmtDur } from "../../frontend/src/components/ui";

describe("format helper", () => {
  it("fmtBytes memakai satuan yang sesuai", () => {
    expect(fmtBytes(0)).toMatch(/^0/);
    expect(fmtBytes(1024 * 1024)).toMatch(/1(\.0)?\s?MB/);
    expect(fmtBytes(5 * 1024 ** 3)).toMatch(/GB/);
  });
  it("fmtDur memformat menit:detik dan jam", () => {
    expect(fmtDur(65)).toBe("1:05");
    expect(fmtDur(3725)).toMatch(/^1:02:05$/);
    expect(fmtDur(0)).toBe("0:00");
  });
});
