"""PM taxonomy for the Lenny Wisdom indexer.

55+ lowercase-kebab tags spanning strategy, growth, retention, monetization,
product craft, metrics, AI, team/leadership, design, execution, market/users,
and business model domains.
"""

TAXONOMY: set[str] = {
    # Strategy
    "strategy",
    "vision",
    "positioning",
    "competitive-analysis",
    "market-entry",
    "platform-strategy",
    "partnerships",
    # Growth & Acquisition
    "growth",
    "acquisition",
    "activation",
    "onboarding",
    "plg",
    "enterprise-sales",
    "self-serve",
    "virality",
    # Retention & Engagement
    "retention",
    "engagement",
    "churn",
    "habit-formation",
    # Monetization
    "pricing",
    "monetization",
    "packaging",
    "freemium",
    "unit-economics",
    # Product Craft
    "prioritization",
    "roadmapping",
    "user-research",
    "experimentation",
    "mvp",
    "feature-development",
    "product-quality",
    "technical-debt",
    # Metrics & Data
    "metrics",
    "analytics",
    "goal-setting",
    "okrs",
    "north-star-metric",
    # AI & Technology
    "ai-product",
    "ai-strategy",
    "technology-adoption",
    # Team & Leadership
    "hiring",
    "team-building",
    "culture",
    "leadership",
    "pm-career",
    "stakeholder-management",
    "cross-functional",
    "decision-making",
    # Design & UX
    "design",
    "ux",
    "simplicity",
    "accessibility",
    # Execution
    "launch",
    "iteration",
    "scaling",
    "operations",
    "process",
    # Market & Users
    "market-research",
    "segmentation",
    "persona",
    "jobs-to-be-done",
    "customer-development",
    # Business Model
    "business-model",
    "marketplace",
    "saas",
    "b2b",
    "b2c",
    "developer-tools",
}


def validate_tags(tags: list[str]) -> list[str]:
    """Filter *tags* to only those present in the taxonomy."""
    return [t for t in tags if t in TAXONOMY]


def taxonomy_as_prompt_list() -> str:
    """Return the taxonomy as a sorted, comma-joined string for LLM prompts."""
    return ", ".join(sorted(TAXONOMY))
