# Lenny Wisdom MCP Server

MCP server that transforms Lenny's Podcast transcripts into a PM thinking partner.

## Architecture

Three layers:

1. **Indexer Pipeline** (Python) -- Extracts, chunks, and embeds podcast transcripts into structured wisdom
2. **MCP Server** (Cloudflare Workers) -- Serves wisdom via MCP tools using D1 + Vectorize
3. **Claude Code Skills** -- Slash commands that invoke the MCP tools for PM workflows

## Quick Start

### Indexer

```bash
cd indexer
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
lenny-index --help
```

### Worker

```bash
cd worker
npm install
npm run dev
```

Before first deploy, create the D1 database and Vectorize index:

```bash
wrangler d1 create lenny-wisdom-db
wrangler vectorize create lenny-wisdom-vectors --dimensions=1024 --metric=cosine
```

Then update `database_id` in `wrangler.toml` and run migrations:

```bash
npm run db:migrate
npm run deploy
```
