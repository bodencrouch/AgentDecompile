import { describe, expect, it } from "vitest";
import {
  binaryIdentityKey,
  shouldAutoOpenFunction,
} from "./atlasAutoOpen";

describe("binaryIdentityKey", () => {
  it("joins slug, program, and locator", () => {
    expect(
      binaryIdentityKey({ slug: "k1", program: "game.exe", locator: "/tmp/a.gpr" }),
    ).toBe("k1|game.exe|/tmp/a.gpr");
  });

  it("treats missing fields as empty segments", () => {
    expect(binaryIdentityKey({ slug: "k1", program: "", locator: "" })).toBe("k1||");
  });
});

describe("shouldAutoOpenFunction", () => {
  const key = "k1|prog|/tmp/a.gpr";

  it("opens once when scoring rows exist and no addr is selected", () => {
    expect(
      shouldAutoOpenFunction({
        browseOnly: false,
        addr: "",
        rowCount: 3,
        binaryKey: key,
        openedForKey: null,
      }),
    ).toBe(true);
  });

  it("does not re-open for the same binary after a prior auto-open", () => {
    expect(
      shouldAutoOpenFunction({
        browseOnly: false,
        addr: "",
        rowCount: 3,
        binaryKey: key,
        openedForKey: key,
      }),
    ).toBe(false);
  });

  it("opens again when the binary identity changes", () => {
    expect(
      shouldAutoOpenFunction({
        browseOnly: false,
        addr: "",
        rowCount: 2,
        binaryKey: "k2|other|/tmp/b.gpr",
        openedForKey: key,
      }),
    ).toBe(true);
  });

  it("suppresses when browseOnly is set", () => {
    expect(
      shouldAutoOpenFunction({
        browseOnly: true,
        addr: "",
        rowCount: 5,
        binaryKey: key,
        openedForKey: null,
      }),
    ).toBe(false);
  });

  it("suppresses when an address is already selected", () => {
    expect(
      shouldAutoOpenFunction({
        browseOnly: false,
        addr: "0x401000",
        rowCount: 5,
        binaryKey: key,
        openedForKey: null,
      }),
    ).toBe(false);
  });

  it("suppresses when there are no rows", () => {
    expect(
      shouldAutoOpenFunction({
        browseOnly: false,
        addr: "",
        rowCount: 0,
        binaryKey: key,
        openedForKey: null,
      }),
    ).toBe(false);
  });

  it("suppresses when binary key is empty", () => {
    expect(
      shouldAutoOpenFunction({
        browseOnly: false,
        addr: "",
        rowCount: 2,
        binaryKey: "",
        openedForKey: null,
      }),
    ).toBe(false);
  });
});
