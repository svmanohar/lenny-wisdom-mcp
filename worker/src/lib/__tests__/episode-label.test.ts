import { describe, it, expect } from "vitest";
import { episodeLabel, episodeTitle } from "../episode-label";

describe("episodeTitle", () => {
  it("returns the title when present", () => {
    expect(episodeTitle({ title: "Masterclass", guest: "Jane" })).toBe("Masterclass");
  });

  it("falls back to the guest name when title is null", () => {
    expect(episodeTitle({ title: null, guest: "Josh Woodward" })).toBe("Josh Woodward");
  });

  it("falls back to 'Untitled episode' when title and guest are missing", () => {
    expect(episodeTitle({ title: null, guest: null })).toBe("Untitled episode");
  });
});

describe("episodeLabel", () => {
  it("appends the guest when a title exists", () => {
    expect(episodeLabel({ title: "Masterclass", guest: "Jane" })).toBe("Masterclass (Jane)");
  });

  it("returns the title alone when there is no guest", () => {
    expect(episodeLabel({ title: "Masterclass", guest: null })).toBe("Masterclass");
  });

  it("does not duplicate the guest when it replaces a null title", () => {
    expect(episodeLabel({ title: null, guest: "Josh Woodward" })).toBe("Josh Woodward");
  });

  it("returns 'Untitled episode' when both are missing", () => {
    expect(episodeLabel({ title: null, guest: null })).toBe("Untitled episode");
  });
});
