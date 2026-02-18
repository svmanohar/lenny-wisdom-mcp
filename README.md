# Lenny Wisdom MCP

An MCP (Model Context Protocol) server that gives Claude access to 303 episodes of [Lenny's Podcast](https://www.lennyspodcast.com/) — the leading podcast for product managers. Ask it for frameworks, real company examples, coaching on decisions, and vocabulary guidance, all grounded in what guests actually said.

Built on Cloudflare Workers with D1 and Vectorize. Transport: streamable HTTP.

---

## What it does

The server exposes 9 tools across two categories:

**Retrieval** — search the indexed transcript corpus directly
**Reasoning** — retrieve relevant wisdom and synthesize it into structured guidance

```
search_wisdom("how do great PMs prioritize ruthlessly?")
coach_me("we're deciding whether to gate AI features behind enterprise licensing")
challenge_decision("we should kill the free tier to focus on enterprise")
teach_framework("Jobs to be Done")
sharpen_language("we need to move fast" audience="executive")
```

---

## Architecture

```
                          ┌──────────────────────────────────────┐
                          │        Claude Code / MCP Client       │
                          └────────────────┬─────────────────────┘
                                           │ HTTPS + Bearer token
                                           │ streamable-http transport
                          ┌────────────────▼─────────────────────┐
                          │     Cloudflare Worker (TypeScript)    │
                          │                                       │
                          │  ┌─────────────────────────────────┐  │
                          │  │   LennyWisdomMCP (McpAgent DO)  │  │
                          │  │   9 tools registered via MCP SDK│  │
                          │  └────────────┬────────────────────┘  │
                          └──────────────┬┴───────────────────────┘
                                         │
                    ┌────────────────────┼──────────────────────┐
                    │                    │                       │
          ┌─────────▼──────┐  ┌──────────▼───────┐  ┌──────────▼──────┐
          │  Cloudflare D1  │  │  CF Vectorize     │  │   Voyage AI     │
          │  (9 tables)     │  │  1024-dim cosine  │  │  voyage-3       │
          │  structured data│  │  segment vectors  │  │  query embeds   │
          └────────────────┘  └──────────────────┘  └─────────────────┘

Indexing pipeline (runs once, offline):

  Transcript .md files
       │
       ▼
  Parse metadata (YAML frontmatter: guest, title, date, topics)
       │
       ▼
  Haiku — segment into topic-coherent blocks (300–2000 tokens, 75-token overlap)
       │
       ▼
  Haiku — extract guest profile from intro (role, companies, expertise)
       │
       ▼
  Sonnet — extract per segment: frameworks, heuristics, examples,
           communication_patterns, tags (55-tag PM taxonomy), key_quote
       │
       ▼
  Voyage AI — 1024-dim embedding per segment
       │
       ▼
  Upload → D1 (structured rows) + Vectorize (vectors)
```

---

## D1 schema

| Table | Purpose | Key columns |
|---|---|---|
| `episodes` | One row per podcast episode | `title`, `guest`, `date`, `topics` (JSON) |
| `guests` | Structured guest profile | `current_role`, `current_company`, `notable_companies`, `domain_expertise` |
| `segments` | Topic-coherent transcript chunks | `topic`, `speakers`, `content`, `token_count` |
| `frameworks` | Named mental models | `name`, `description`, `source_attribution`, `verbatim_definition` |
| `heuristics` | Rules of thumb | `statement`, `context` |
| `examples` | Company case studies | `company`, `situation`, `outcome` |
| `communication_patterns` | How-to-say-it advice | `technique`, `audience`, `example` |
| `tags` | PM taxonomy tags per segment | 55 tags: `pricing`, `growth`, `hiring`, etc. |
| `quotes` | Key quotes per segment | `quote`, `speaker` |

---

## Tools reference

### Retrieval tools

#### `search_wisdom`
Semantic search across all podcast wisdom. Embeds the query with Voyage AI, queries Vectorize, optionally filters by PM taxonomy tag, enriches results from D1.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | yes | Natural language search query |
| `tag_filter` | string | no | PM taxonomy tag (e.g. `pricing`, `growth`) |
| `max_results` | integer 1–20 | no | Number of results (default 5) |
| `format` | `concise` \| `detailed` | no | Response verbosity (default `concise`) |

#### `find_frameworks`
Search named frameworks and mental models by name or topic.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | yes | Framework name or topic |
| `max_results` | integer 1–20 | no | Number of results (default 5) |

#### `find_examples`
Find real company case studies. At least one of `company` or `topic` should be provided.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `company` | string | no | Company name (e.g. `Notion`, `Figma`) |
| `topic` | string | no | PM topic to filter by |
| `max_results` | integer 1–20 | no | Number of results (default 5) |

#### `get_episode_context`
Retrieve all extracted data for a specific episode. At least one identifier is required.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `guest` | string | no | Guest name |
| `episode_number` | integer | no | Episode number |
| `title` | string | no | Episode title (partial match) |

#### `list_guests`
Browse guests with episode counts, optionally filtered by PM topic.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `topic` | string | no | PM taxonomy topic to filter by |
| `max_results` | integer 1–50 | no | Number of results |

### Reasoning tools

These tools retrieve relevant wisdom from the corpus and synthesize a structured response.

#### `coach_me`
Walk through a product decision using relevant frameworks from the podcast.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `situation` | string | yes | Your product situation or decision (1–3 sentences) |
| `goal` | string | no | The outcome you're trying to achieve |
| `role` | string | no | Your role (e.g. `PM`, `founder`, `designer`) |
| `max_sources` | integer 1–10 | no | Source segments to draw from |

#### `challenge_decision`
Red-team a decision using counterarguments from podcast guests.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `decision` | string | yes | The decision you plan to make |
| `context` | string | no | Context and reasoning |
| `alternatives` | string[] | no | Alternative options considered |
| `max_sources` | integer 1–10 | no | Source segments to draw from |

#### `teach_framework`
Deep-learn a PM framework using the podcast as the source.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `framework` | string | yes | Framework to learn (e.g. `Jobs to be Done`, `LNO Framework`) |
| `depth` | `overview` \| `detailed` \| `masterclass` | no | Learning depth (default `overview`) |

#### `sharpen_language`
Vocabulary and audience-aware reframing for product communication.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `message` | string | yes | Your rough phrasing of the concept |
| `audience` | string | yes | Target audience: `executive`, `engineering`, `customer`, `peer-pm`, `investor` |
| `context` | string | no | Additional context |
| `max_sources` | integer 1–10 | no | Source segments to draw from |

---

## Setup

Two independent components: the **Worker** (serves the MCP endpoint) and the **Indexer** (populates the database).

### Prerequisites

- [Node.js](https://nodejs.org/) 18+
- [Wrangler CLI](https://developers.cloudflare.com/workers/wrangler/install-and-update/) (`wrangler login`)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for Python dependency management
- Cloudflare account with Workers, D1, and Vectorize access
- API keys for [Anthropic](https://console.anthropic.com/) and [Voyage AI](https://dash.voyageai.com/)

### 1. Clone the repo

```bash
git clone https://github.com/svmanohar/lenny-wisdom-mcp.git
cd lenny-wisdom-mcp
```

### 2. Worker setup

```bash
cd worker
npm install
```

#### Create Cloudflare resources

```bash
# Create D1 database
wrangler d1 create lenny-wisdom-db

# Create Vectorize index
wrangler vectorize create lenny-wisdom-vectors --dimensions=1024 --metric=cosine
```

Update `wrangler.toml` with the `database_id` from the D1 create output.

#### Run migrations

```bash
npm run db:migrate
```

#### Set secrets

```bash
wrangler secret put MCP_AUTH_TOKEN     # Bearer token for MCP clients
wrangler secret put VOYAGE_API_KEY     # Voyage AI key for query-time embeddings
```

#### Deploy

```bash
npm run deploy
```

Verify: `curl https://lenny-wisdom-mcp.<your-subdomain>.workers.dev/health`

### 3. Indexer setup

```bash
cd indexer
uv sync
```

> **Python 3.14 is not supported.** The `voyageai` and `anthropic` packages break on 3.14. Always use `uv run` — it picks 3.13 automatically.

#### Environment variables

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export VOYAGE_API_KEY="pa-..."
export CF_ACCOUNT_ID="<your-account-id>"
export CF_DB_ID="<your-d1-database-id>"
export CF_API_TOKEN="<your-cf-api-token>"
```

> **Important:** The CF API token must be created at [dash.cloudflare.com/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens). The OAuth token from `wrangler login` cannot write to D1 via the REST API. Use the "Edit Cloudflare Workers" template and add D1 Edit + Vectorize Edit permissions.

#### Run the pipeline

```bash
# Dry run (no upload)
uv run python -m indexer.run --transcripts /path/to/episodes --limit 5 --dry-run

# Live run on 5 episodes
uv run python -m indexer.run --transcripts /path/to/episodes --limit 5

# Full corpus (303 episodes, ~10-15 min with default concurrency)
uv run python -m indexer.run --transcripts /path/to/episodes
```

#### Concurrency tuning

The pipeline processes episodes concurrently. Tune via CLI flags or env vars:

| Flag | Env var | Default | Description |
|---|---|---|---|
| `--episode-concurrency` | `LENNY_EPISODE_CONCURRENCY` | 10 | Max episodes processed at once |
| `--sonnet-concurrency` | `LENNY_SONNET_CONCURRENCY` | 50 | Max concurrent Sonnet API calls |
| `--voyage-concurrency` | `LENNY_VOYAGE_CONCURRENCY` | 5 | Max concurrent Voyage API calls |

If you hit API rate limits, reduce `--episode-concurrency` first.

### 4. Configure Claude Code

Add to `~/.claude/mcp_servers.json` (global) or `.mcp.json` (project-scoped):

```json
{
  "lenny-wisdom": {
    "type": "http",
    "url": "https://lenny-wisdom-mcp.<your-subdomain>.workers.dev/mcp",
    "headers": {
      "Authorization": "Bearer <your-mcp-auth-token>"
    }
  }
}
```

Restart Claude Code after editing the config.

---

## Local development

```bash
cd worker
npm run dev    # Starts wrangler dev server
npm test       # 31 vitest tests

cd ../indexer
uv run pytest  # 49 pytest tests (all API clients mocked)
```

> **Note:** `wrangler dev --local` cannot emulate Vectorize or Workers AI. Vector search paths will not work locally. D1 is emulated and works fine.

---

## Known gotchas

- **Python 3.14 breaks voyageai/anthropic** — always use `uv run`
- **CF OAuth token != API token** — `wrangler login` token can't do D1 REST writes; create a separate API token
- **Auth returns 403, not 401** — 401 triggers MCP SDK OAuth flow; bearer token auth uses 403
- **`nodejs_compat` required** — the `agents` package needs this compatibility flag in `wrangler.toml`
- **`ExtractedExample.company` is nullable** — Sonnet occasionally returns null for the company field

---

## Project structure

```
lenny-wisdom-mcp/
├── worker/                         # Cloudflare Worker
│   ├── src/
│   │   ├── index.ts                # McpAgent DO + fetch handler
│   │   ├── db/
│   │   │   ├── queries.ts          # D1 queries
│   │   │   └── schema.sql          # 9-table schema
│   │   ├── lib/
│   │   │   ├── types.ts            # TypeScript interfaces
│   │   │   ├── format.ts           # Markdown formatters
│   │   │   └── vector-search.ts    # Voyage query embedding + Vectorize search
│   │   └── tools/                  # One file per MCP tool
│   ├── wrangler.toml
│   └── package.json
├── indexer/                        # Python indexing pipeline
│   ├── indexer/
│   │   ├── run.py                  # CLI entrypoint (click)
│   │   ├── parse.py                # Transcript parser
│   │   ├── segment.py              # Haiku segmentation
│   │   ├── extract.py              # Sonnet extraction
│   │   ├── embed.py                # Voyage AI embeddings
│   │   ├── upload.py               # D1 + Vectorize upload
│   │   ├── guest.py                # Guest profile extraction
│   │   ├── models.py               # Pydantic models
│   │   └── taxonomy.py             # 55 PM taxonomy tags
│   └── pyproject.toml
└── HANDOVER.md
```
