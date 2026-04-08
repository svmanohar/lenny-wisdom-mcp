import { McpAgent } from "agents/mcp";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import type { Env, AuthContext } from "./lib/types";
import { authenticate } from "./lib/auth";
import { handleRegister } from "./lib/register";
import { checkRegisterRateLimit } from "./lib/register-rate-limit";
import { RateLimitError } from "./lib/guarded-vector-query";

// Props passed from the outer fetch handler to the DO via ctx.props
interface AuthProps extends Record<string, unknown> {
  tokenId: string;
  tier: string;
  voyageApiKey: string | null;
  dailyLimit: number;
}
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
export class LennyWisdomMCP extends McpAgent<Env, unknown, AuthProps> {
  server = new McpServer({ name: "lenny-wisdom", version: "0.2.0" });

  async init() {
    // Read auth context from props, set by the outer fetch handler via ctx.props.
    // The agents SDK passes ctx.props → getAgentByName() → onStart() → this.props.
    const authCtx: AuthContext = this.props
      ? {
          tokenId: this.props.tokenId,
          tier: this.props.tier as AuthContext["tier"],
          voyageApiKey: this.props.voyageApiKey,
          dailyLimit: this.props.dailyLimit,
        }
      : {
          tokenId: "admin",
          tier: "admin",
          voyageApiKey: null,
          dailyLimit: Infinity,
        };

    // Helper: wrap vector-search tool handlers to catch RateLimitError
    function wrapVectorTool<T>(
      handler: (args: T, env: Env, auth: AuthContext) => Promise<string>
    ) {
      return async (args: T, env: Env) => {
        try {
          return await handler(args, env, authCtx);
        } catch (err) {
          if (err instanceof RateLimitError) {
            return `⚠️ ${err.message}`;
          }
          throw err;
        }
      };
    }

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
      async ({ query, tag_filter, max_results, format }) => {
        const wrapped = wrapVectorTool(handleSearchWisdom);
        const text = await wrapped(
          { query, tag_filter, max_results, format },
          this.env
        );
        return {
          content: [{ type: "text" as const, text }],
          isError: text.startsWith("⚠️"),
        };
      }
    );

    this.server.tool(
      "find_frameworks",
      "Search for named frameworks and mental models from Lenny's Podcast guests. Returns framework names, descriptions, and source attribution.",
      {
        query: z
          .string()
          .max(40)
          .describe("Short keyword or framework name to search for (e.g. 'pricing', 'JTBD', 'north star metric'). Keep under 40 chars — this is a keyword match, not semantic search."),
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
          .max(40)
          .optional()
          .describe("Company name keyword (e.g. 'Spotify', 'Airbnb'). Short name only."),
        topic: z
          .string()
          .max(40)
          .optional()
          .describe("PM topic keyword (e.g. 'growth', 'onboarding'). Short keyword only."),
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
        guest: z.string().max(40).optional().describe("Guest name (e.g. 'Shreyas Doshi', 'Lenny')"),
        episode_number: z
          .number()
          .int()
          .optional()
          .describe("Episode number"),
        title: z
          .string()
          .max(40)
          .optional()
          .describe("Short title keyword (e.g. 'north star metric'). Keep under 40 chars."),
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
          .max(40)
          .optional()
          .describe("PM topic keyword to filter by (e.g. 'pricing', 'retention'). Short keyword only."),
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

    // --- Reasoning Tools (vector-search, rate-limited) ---

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
      async ({ situation, goal, role, max_sources }) => {
        const wrapped = wrapVectorTool(handleCoachMe);
        const text = await wrapped(
          { situation, goal, role, max_sources },
          this.env
        );
        return {
          content: [{ type: "text" as const, text }],
          isError: text.startsWith("⚠️"),
        };
      }
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
      async ({ decision, context, alternatives, max_sources }) => {
        const wrapped = wrapVectorTool(handleChallengeDecision);
        const text = await wrapped(
          { decision, context, alternatives, max_sources },
          this.env
        );
        return {
          content: [{ type: "text" as const, text }],
          isError: text.startsWith("⚠️"),
        };
      }
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
      async ({ framework, depth }) => {
        const wrapped = wrapVectorTool(handleTeachFramework);
        const text = await wrapped({ framework, depth }, this.env);
        return {
          content: [{ type: "text" as const, text }],
          isError: text.startsWith("⚠️"),
        };
      }
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
          .max(40)
          .optional()
          .describe("Short context keyword for pattern matching (e.g. 'board presentation', 'sprint review'). Keep under 40 chars — long context goes in the message field instead."),
        max_sources: z
          .number()
          .int()
          .min(1)
          .max(10)
          .optional()
          .describe("Maximum source segments to draw from"),
      },
      async ({ message, audience, context, max_sources }) => {
        const wrapped = wrapVectorTool(handleSharpenLanguage);
        const text = await wrapped(
          { message, audience, context, max_sources },
          this.env
        );
        return {
          content: [{ type: "text" as const, text }],
          isError: text.startsWith("⚠️"),
        };
      }
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

    // Self-service registration — no auth required, rate-limited by IP
    if (url.pathname === "/register") {
      const rateLimited = await checkRegisterRateLimit(request, env);
      if (rateLimited) return rateLimited;
      return handleRegister(request, env);
    }

    // Everything below requires auth
    const authResult = await authenticate(request, env);
    if (authResult instanceof Response) {
      return authResult;
    }

    // Only /mcp is a valid authenticated endpoint
    if (url.pathname !== "/mcp") {
      return new Response(JSON.stringify({ error: "not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Inject auth context as props for the DO to read.
    // The agents SDK reads ctx.props and passes to the DO via getAgentByName().
    (ctx as unknown as { props: AuthProps }).props = {
      tokenId: authResult.tokenId,
      tier: authResult.tier,
      voyageApiKey: authResult.voyageApiKey,
      dailyLimit: authResult.dailyLimit,
    };

    return mcpHandler.fetch(request, env, ctx);
  },
};
