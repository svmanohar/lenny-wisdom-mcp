import { McpAgent } from "agents/mcp";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import type { Env } from "./lib/types";
import {
  handleSearchWisdom,
  handleFindFrameworks,
  handleFindExamples,
  handleGetEpisode,
  handleListGuests,
  handleCoachMe,
  handleChallengeDecision,
  handleTeachFramework,
  handleSharpenLanguage,
} from "./tools";

// McpAgent Durable Object — each session gets its own instance with
// its own McpServer and transport. Uses streamable-http (default in v0.5.0).
export class LennyWisdomMCP extends McpAgent<Env> {
  server = new McpServer({ name: "lenny-wisdom", version: "0.1.0" });

  async init() {
    // --- Retrieval Tools ---

    this.server.tool(
      "search_wisdom",
      "Semantic search across all Lenny's Podcast wisdom. Returns frameworks, heuristics, examples, and quotes relevant to a product management question.",
      {
        query: z.string().describe("Natural language search query"),
        tag_filter: z
          .string()
          .optional()
          .describe(
            "Filter by PM taxonomy tag (e.g. 'growth', 'pricing', 'strategy')"
          ),
        max_results: z
          .number()
          .int()
          .min(1)
          .max(20)
          .optional()
          .describe("Maximum results to return (default 5)"),
        format: z
          .enum(["concise", "detailed"])
          .optional()
          .describe("Response format (default concise)"),
      },
      async ({ query, tag_filter, max_results, format }) => ({
        content: [
          {
            type: "text" as const,
            text: await handleSearchWisdom(
              { query, tag_filter, max_results, format },
              this.env
            ),
          },
        ],
      })
    );

    this.server.tool(
      "find_frameworks",
      "Search for named frameworks and mental models from Lenny's Podcast guests. Returns framework names, descriptions, and source attribution.",
      {
        query: z
          .string()
          .describe("Framework name or topic to search for"),
        max_results: z
          .number()
          .int()
          .min(1)
          .max(20)
          .optional()
          .describe("Maximum results to return (default 5)"),
      },
      async ({ query, max_results }) => ({
        content: [
          {
            type: "text" as const,
            text: await handleFindFrameworks(
              { query, max_results },
              this.env
            ),
          },
        ],
      })
    );

    this.server.tool(
      "find_examples",
      "Find real company examples and case studies discussed on Lenny's Podcast.",
      {
        company: z
          .string()
          .optional()
          .describe("Company name to search for"),
        topic: z
          .string()
          .optional()
          .describe("PM topic to filter examples by"),
        max_results: z
          .number()
          .int()
          .min(1)
          .max(20)
          .optional()
          .describe("Maximum results to return (default 5)"),
      },
      async ({ company, topic, max_results }) => ({
        content: [
          {
            type: "text" as const,
            text: await handleFindExamples(
              { company, topic, max_results },
              this.env
            ),
          },
        ],
      })
    );

    this.server.tool(
      "get_episode_context",
      "Get full context for a specific episode: all segments, frameworks, examples, and quotes.",
      {
        guest: z.string().optional().describe("Guest name to look up"),
        episode_number: z
          .number()
          .int()
          .optional()
          .describe("Episode number"),
        title: z
          .string()
          .optional()
          .describe("Episode title to search for"),
      },
      async ({ guest, episode_number, title }) => ({
        content: [
          {
            type: "text" as const,
            text: await handleGetEpisode(
              { guest, episode_number, title },
              this.env
            ),
          },
        ],
      })
    );

    this.server.tool(
      "list_guests",
      "List podcast guests, optionally filtered by topic. Shows guest names with episode counts.",
      {
        topic: z
          .string()
          .optional()
          .describe("Filter guests by PM taxonomy topic"),
        max_results: z
          .number()
          .int()
          .min(1)
          .max(50)
          .optional()
          .describe("Maximum results to return"),
      },
      async ({ topic, max_results }) => ({
        content: [
          {
            type: "text" as const,
            text: await handleListGuests({ topic, max_results }, this.env),
          },
        ],
      })
    );

    // --- Reasoning Tools ---

    this.server.tool(
      "coach_me",
      "Walk through a product decision using relevant frameworks from Lenny's Podcast. Retrieves wisdom, applies it to your situation, and guides structured thinking.",
      {
        situation: z
          .string()
          .describe(
            "Describe your product situation or decision in 1-3 sentences"
          ),
        goal: z
          .string()
          .optional()
          .describe("What outcome are you trying to achieve?"),
        role: z
          .string()
          .optional()
          .describe("Your role (e.g. PM, founder, designer)"),
        max_sources: z
          .number()
          .int()
          .min(1)
          .max(10)
          .optional()
          .describe("Maximum source segments to draw from"),
      },
      async ({ situation, goal, role, max_sources }) => ({
        content: [
          {
            type: "text" as const,
            text: await handleCoachMe(
              { situation, goal, role, max_sources },
              this.env
            ),
          },
        ],
      })
    );

    this.server.tool(
      "challenge_decision",
      "Red-team a product decision using counterarguments from Lenny's Podcast guests. Stress-tests your reasoning before you commit.",
      {
        decision: z
          .string()
          .describe("The decision you're planning to make"),
        context: z
          .string()
          .optional()
          .describe("Context and reasoning for this decision"),
        alternatives: z
          .array(z.string())
          .optional()
          .describe("Alternative options you considered"),
        max_sources: z
          .number()
          .int()
          .min(1)
          .max(10)
          .optional()
          .describe("Maximum source segments to draw from"),
      },
      async ({ decision, context, alternatives, max_sources }) => ({
        content: [
          {
            type: "text" as const,
            text: await handleChallengeDecision(
              { decision, context, alternatives, max_sources },
              this.env
            ),
          },
        ],
      })
    );

    this.server.tool(
      "teach_framework",
      "Deep-learn a PM framework using Lenny's Podcast as the textbook. Provides definitions, real examples, when to use, and practice prompts.",
      {
        framework: z
          .string()
          .describe(
            "Framework or concept to learn (e.g. 'Jobs to be Done', 'LNO Framework')"
          ),
        depth: z
          .enum(["overview", "detailed", "masterclass"])
          .optional()
          .describe("Learning depth (default overview)"),
      },
      async ({ framework, depth }) => ({
        content: [
          {
            type: "text" as const,
            text: await handleTeachFramework(
              { framework, depth },
              this.env
            ),
          },
        ],
      })
    );

    this.server.tool(
      "sharpen_language",
      "Get vocabulary coaching and audience-aware reframing for product communication, grounded in Lenny's Podcast wisdom.",
      {
        message: z
          .string()
          .describe("Your rough phrasing of the concept"),
        audience: z
          .string()
          .describe(
            "Target audience (e.g. executive, engineering, customer, peer-pm, investor)"
          ),
        context: z
          .string()
          .optional()
          .describe("Additional context for the communication"),
        max_sources: z
          .number()
          .int()
          .min(1)
          .max(10)
          .optional()
          .describe("Maximum source segments to draw from"),
      },
      async ({ message, audience, context, max_sources }) => ({
        content: [
          {
            type: "text" as const,
            text: await handleSharpenLanguage(
              { message, audience, context, max_sources },
              this.env
            ),
          },
        ],
      })
    );
  }
}

// McpAgent.serve() defaults to streamable-http in v0.5.0.
// Each session gets its own DO instance → no shared-server issues.
const mcpHandler = LennyWisdomMCP.serve("/mcp", { binding: "MCP_AGENT" });

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext) {
    const url = new URL(request.url);

    // Health check — no auth required
    if (url.pathname === "/health") {
      return new Response(JSON.stringify({ status: "ok" }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    // Bearer token auth for /mcp endpoint.
    // Uses 403 (not 401) to avoid triggering the MCP SDK's OAuth negotiation flow.
    const authHeader = request.headers.get("Authorization");
    if (!authHeader || authHeader !== `Bearer ${env.MCP_AUTH_TOKEN}`) {
      return new Response(JSON.stringify({ error: "forbidden" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Only /mcp is a valid endpoint — reject everything else with JSON 404.
    if (url.pathname !== "/mcp") {
      return new Response(JSON.stringify({ error: "not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }

    return mcpHandler.fetch(request, env, ctx);
  },
};
