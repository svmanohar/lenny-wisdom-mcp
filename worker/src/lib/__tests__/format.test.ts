import { describe, it, expect } from "vitest";
import { formatSearchResults, formatFrameworks, formatExamples } from "../format";
import type {
  SearchResult,
  Episode,
  Segment,
  Framework,
  Heuristic,
  Example,
  CommunicationPattern,
} from "../types";

// ── helpers to build mock objects ──

function makeEpisode(overrides: Partial<Episode> = {}): Episode {
  return {
    id: 1,
    episode_number: 42,
    title: "Prioritization Masterclass",
    guest: "Shreyas Doshi",
    date: "2024-01-15",
    source_file: "ep42.md",
    topics: ["prioritization", "frameworks"],
    ...overrides,
  };
}

function makeSegment(overrides: Partial<Segment> = {}): Segment {
  return {
    id: "ep-1-seg-0",
    episode_id: 1,
    segment_index: 0,
    topic: "The LNO Framework",
    speakers: ["Lenny", "Shreyas Doshi"],
    content: "Shreyas explains the LNO framework for task prioritization.",
    token_count: 50,
    ...overrides,
  };
}

function makeFramework(overrides: Partial<Framework> = {}): Framework {
  return {
    id: 1,
    segment_id: "ep-1-seg-0",
    name: "LNO Framework",
    description: "Categorize tasks as Leverage, Neutral, or Overhead",
    source_attribution: "Shreyas Doshi",
    verbatim_definition: "L is for Leverage, N is Neutral, O is Overhead",
    ...overrides,
  };
}

function makeHeuristic(overrides: Partial<Heuristic> = {}): Heuristic {
  return {
    id: 1,
    segment_id: "ep-1-seg-0",
    statement: "Small delta means overhead work",
    context: "Helping PMs stop over-investing",
    ...overrides,
  };
}

function makeExample(overrides: Partial<Example> = {}): Example {
  return {
    id: 1,
    segment_id: "ep-1-seg-0",
    company: "Stripe",
    situation: "Treated API docs as Leverage work",
    outcome: "Documentation became competitive moat",
    ...overrides,
  };
}

function makeCommunicationPattern(
  overrides: Partial<CommunicationPattern> = {}
): CommunicationPattern {
  return {
    id: 1,
    segment_id: "ep-1-seg-0",
    technique: "Frame prioritization as impact delta",
    audience: "peer-pm",
    example: "What's the delta between A+ and B-?",
    source_attribution: "Shreyas Doshi",
    ...overrides,
  };
}

function makeSearchResult(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    segment: makeSegment(),
    episode: makeEpisode(),
    frameworks: [makeFramework()],
    heuristics: [makeHeuristic()],
    examples: [makeExample()],
    communication_patterns: [makeCommunicationPattern()],
    tags: ["prioritization", "decision-making"],
    key_quote: "That single decision changed how the entire team allocated time.",
    relevance_score: 0.92,
    ...overrides,
  };
}

// ── formatSearchResults ──

describe("formatSearchResults", () => {
  it("returns 'No results found.' for empty array", () => {
    expect(formatSearchResults([])).toBe("No results found.");
  });

  it("formats a single concise result with all fields", () => {
    const result = formatSearchResults([makeSearchResult()]);
    expect(result).toContain("## 1.");
    expect(result).toContain("Episode #42");
    expect(result).toContain("Prioritization Masterclass");
    expect(result).toContain("(Shreyas Doshi)");
    expect(result).toContain("relevance: 0.92");
    expect(result).toContain("**Topic:** The LNO Framework");
    expect(result).toContain('"That single decision changed');
    expect(result).toContain("**Frameworks:** LNO Framework");
    expect(result).toContain("Small delta means overhead work");
    expect(result).toContain("*Tags: prioritization, decision-making*");
  });

  it("formats multiple results separated by ---", () => {
    const results = [
      makeSearchResult(),
      makeSearchResult({
        segment: makeSegment({ topic: "Career Growth" }),
        relevance_score: 0.85,
      }),
    ];
    const output = formatSearchResults(results);
    expect(output).toContain("## 1.");
    expect(output).toContain("## 2.");
    expect(output).toContain("---");
    expect(output).toContain("Career Growth");
  });

  it("handles detailed format with long content truncation", () => {
    const longContent = "A".repeat(1000);
    const result = formatSearchResults(
      [makeSearchResult({ segment: makeSegment({ content: longContent }) })],
      "detailed"
    );
    expect(result).toContain("...");
    expect(result).toContain("**Content:**");
    expect(result).toContain("**Speakers:** Lenny, Shreyas Doshi");
  });

  it("handles detailed format with communication patterns", () => {
    const result = formatSearchResults([makeSearchResult()], "detailed");
    expect(result).toContain("### Communication Patterns");
    expect(result).toContain("Frame prioritization as impact delta");
    expect(result).toContain("(audience: peer-pm)");
  });

  it("handles result with null episode", () => {
    const result = formatSearchResults([makeSearchResult({ episode: null })]);
    expect(result).toContain("Unknown episode");
  });

  it("handles episode with null episode_number", () => {
    const result = formatSearchResults([
      makeSearchResult({ episode: makeEpisode({ episode_number: null }) }),
    ]);
    expect(result).toContain("Episode:");
    expect(result).not.toContain("#null");
  });

  it("handles episode with null guest", () => {
    const result = formatSearchResults([
      makeSearchResult({ episode: makeEpisode({ guest: null }) }),
    ]);
    // Should not include guest parenthetical
    expect(result).not.toContain("(null)");
  });

  it("handles result with zero relevance score", () => {
    const result = formatSearchResults([
      makeSearchResult({ relevance_score: 0 }),
    ]);
    expect(result).not.toContain("relevance:");
  });

  it("handles result with no frameworks", () => {
    const result = formatSearchResults([
      makeSearchResult({ frameworks: [] }),
    ]);
    expect(result).not.toContain("**Frameworks:**");
  });

  it("handles result with no heuristics", () => {
    const result = formatSearchResults([
      makeSearchResult({ heuristics: [] }),
    ]);
    expect(result).not.toContain("**Key heuristics:**");
  });

  it("handles result with no key_quote", () => {
    const result = formatSearchResults([
      makeSearchResult({ key_quote: null }),
    ]);
    expect(result).not.toContain('> "');
  });

  it("handles result with no tags", () => {
    const result = formatSearchResults([makeSearchResult({ tags: [] })]);
    expect(result).not.toContain("*Tags:");
  });

  it("truncates heuristics to 3 in concise mode", () => {
    const heuristics = Array.from({ length: 5 }, (_, i) =>
      makeHeuristic({ id: i, statement: `Heuristic ${i}` })
    );
    const result = formatSearchResults([
      makeSearchResult({ heuristics }),
    ]);
    expect(result).toContain("Heuristic 0");
    expect(result).toContain("Heuristic 2");
    expect(result).not.toContain("Heuristic 3");
  });

  it("shows all heuristics in detailed mode", () => {
    const heuristics = Array.from({ length: 5 }, (_, i) =>
      makeHeuristic({ id: i, statement: `Heuristic ${i}` })
    );
    const result = formatSearchResults(
      [makeSearchResult({ heuristics })],
      "detailed"
    );
    expect(result).toContain("Heuristic 4");
  });

  it("detailed mode shows heuristic context when present", () => {
    const result = formatSearchResults([makeSearchResult()], "detailed");
    expect(result).toContain("*(Helping PMs stop over-investing)*");
  });

  it("detailed mode handles heuristic with null context", () => {
    const result = formatSearchResults(
      [makeSearchResult({ heuristics: [makeHeuristic({ context: null })] })],
      "detailed"
    );
    expect(result).toContain("Small delta means overhead work");
    expect(result).not.toContain("*(null)*");
  });

  it("detailed mode shows examples with outcome", () => {
    const result = formatSearchResults([makeSearchResult()], "detailed");
    expect(result).toContain("**Stripe**");
    expect(result).toContain("→ Documentation became competitive moat");
  });

  it("detailed mode handles example with null outcome", () => {
    const result = formatSearchResults(
      [makeSearchResult({ examples: [makeExample({ outcome: null })] })],
      "detailed"
    );
    expect(result).toContain("**Stripe**");
    expect(result).not.toContain("→");
  });

  it("detailed mode handles communication pattern with null audience and example", () => {
    const result = formatSearchResults(
      [
        makeSearchResult({
          communication_patterns: [
            makeCommunicationPattern({ audience: null, example: null }),
          ],
        }),
      ],
      "detailed"
    );
    expect(result).toContain("Frame prioritization as impact delta");
    expect(result).not.toContain("(audience:");
  });

  it("handles empty arrays for all enrichment fields", () => {
    const result = formatSearchResults([
      makeSearchResult({
        frameworks: [],
        heuristics: [],
        examples: [],
        communication_patterns: [],
        tags: [],
        key_quote: null,
      }),
    ]);
    expect(result).toContain("**Topic:**");
    expect(result).not.toContain("**Frameworks:**");
    expect(result).not.toContain("**Key heuristics:**");
    expect(result).not.toContain("*Tags:");
  });
});

// ── formatFrameworks ──

describe("formatFrameworks", () => {
  it("returns 'No frameworks found.' for empty array", () => {
    expect(formatFrameworks([])).toBe("No frameworks found.");
  });

  it("formats a single framework with all fields", () => {
    const result = formatFrameworks([makeFramework()]);
    expect(result).toContain("### LNO Framework");
    expect(result).toContain("Categorize tasks as Leverage, Neutral, or Overhead");
    expect(result).toContain('> "L is for Leverage, N is Neutral, O is Overhead"');
    expect(result).toContain("*Source: Shreyas Doshi*");
  });

  it("formats framework without verbatim_definition", () => {
    const result = formatFrameworks([
      makeFramework({ verbatim_definition: null }),
    ]);
    expect(result).toContain("### LNO Framework");
    expect(result).not.toContain('> "');
  });

  it("formats framework without source_attribution", () => {
    const result = formatFrameworks([
      makeFramework({ source_attribution: null }),
    ]);
    expect(result).toContain("### LNO Framework");
    expect(result).not.toContain("*Source:");
  });

  it("formats framework with no optional fields", () => {
    const result = formatFrameworks([
      makeFramework({ verbatim_definition: null, source_attribution: null }),
    ]);
    expect(result).toBe(
      "### LNO Framework\n\nCategorize tasks as Leverage, Neutral, or Overhead"
    );
  });

  it("formats multiple frameworks separated by ---", () => {
    const result = formatFrameworks([
      makeFramework(),
      makeFramework({ id: 2, name: "RICE Scoring" }),
    ]);
    expect(result).toContain("### LNO Framework");
    expect(result).toContain("---");
    expect(result).toContain("### RICE Scoring");
  });
});

// ── formatExamples ──

describe("formatExamples", () => {
  it("returns 'No examples found.' for empty array", () => {
    expect(formatExamples([])).toBe("No examples found.");
  });

  it("formats a single example with outcome", () => {
    const result = formatExamples([makeExample()]);
    expect(result).toContain("### Stripe");
    expect(result).toContain("**Situation:** Treated API docs as Leverage work");
    expect(result).toContain("**Outcome:** Documentation became competitive moat");
  });

  it("formats example without outcome", () => {
    const result = formatExamples([makeExample({ outcome: null })]);
    expect(result).toContain("### Stripe");
    expect(result).toContain("**Situation:**");
    expect(result).not.toContain("**Outcome:**");
  });

  it("formats multiple examples separated by ---", () => {
    const result = formatExamples([
      makeExample(),
      makeExample({ id: 2, company: "Airbnb", situation: "Focused on host experience" }),
    ]);
    expect(result).toContain("### Stripe");
    expect(result).toContain("---");
    expect(result).toContain("### Airbnb");
  });
});
