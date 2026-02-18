"""Sync new transcripts from Lenny's Dropbox shared folder and run the indexing pipeline.

Downloads .txt files directly into the transcripts directory. The pipeline handles
.txt files natively (no frontmatter needed — guest name inferred from filename).

Authentication uses a refresh token stored at ~/.lenny-wisdom/dropbox_token.json
(created by dropbox_auth.py). Access tokens are refreshed automatically.

Usage:
    uv run python sync_dropbox.py [--dry-run]

Environment variables (for the indexing pipeline):
    ANTHROPIC_API_KEY   — For Haiku + Sonnet
    VOYAGE_API_KEY      — For embeddings
    CF_ACCOUNT_ID       — Cloudflare account ID
    CF_DB_ID            — D1 database ID
    CF_API_TOKEN        — Cloudflare API token (D1 + Vectorize write)
"""

import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import httpx

SHARED_URL = (
    "https://www.dropbox.com/scl/fo/yxi4s2w998p1gvtpu4193/"
    "AMdNPR8AOw0lMklwtnC0TrQ?rlkey=j06x0nipoti519e0xgm23zsn9&e=1&dl=0"
)
TRANSCRIPTS_DIR = Path(
    os.getenv(
        "TRANSCRIPTS_DIR",
        "/Users/sasha/Documents/local-development/lenny-transcripts/episodes",
    )
)
INDEXER_DIR = Path(__file__).parent
TOKEN_FILE = Path.home() / ".lenny-wisdom" / "dropbox_token.json"


# ── Dropbox auth ─────────────────────────────────────────────────────────


def get_dropbox_token() -> str:
    """Get a fresh Dropbox access token using the stored refresh token."""
    if not TOKEN_FILE.exists():
        raise SystemExit(
            f"No Dropbox credentials found at {TOKEN_FILE}\n"
            "Run: uv run python dropbox_auth.py"
        )

    creds = json.loads(TOKEN_FILE.read_text())
    refresh_token = creds["refresh_token"]
    app_key = creds["app_key"]
    app_secret = creds["app_secret"]

    resp = httpx.post(
        "https://api.dropboxapi.com/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": app_key,
            "client_secret": app_secret,
        },
    )

    if not resp.is_success:
        raise SystemExit(
            f"Failed to refresh Dropbox token: {resp.status_code} — {resp.text}\n"
            "Re-run: uv run python dropbox_auth.py"
        )

    return resp.json()["access_token"]


# ── Dropbox file operations ──────────────────────────────────────────────


def list_dropbox_files(token: str) -> list[dict]:
    """List all .txt files in the shared Dropbox folder."""
    files = []
    url = "https://api.dropboxapi.com/2/files/list_folder"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {"path": "", "shared_link": {"url": SHARED_URL}, "limit": 2000}

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        files.extend(data.get("entries", []))

        while data.get("has_more"):
            resp = client.post(
                "https://api.dropboxapi.com/2/files/list_folder/continue",
                headers=headers,
                json={"cursor": data["cursor"]},
            )
            resp.raise_for_status()
            data = resp.json()
            files.extend(data.get("entries", []))

    return [f for f in files if f["name"].endswith(".txt")]


def download_file(token: str, filename: str) -> str:
    """Download a single file from the shared Dropbox folder."""
    url = "https://content.dropboxapi.com/2/sharing/get_shared_link_file"
    api_arg = json.dumps({"url": SHARED_URL, "path": f"/{filename}"})
    headers = {
        "Authorization": f"Bearer {token}",
        "Dropbox-API-Arg": api_arg,
    }

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, headers=headers)
        resp.raise_for_status()
        return resp.text


# ── Delta detection ──────────────────────────────────────────────────────


def slugify(name: str) -> str:
    """Convert a guest name to a directory slug.

    'Gibson Biddle' → 'gibson-biddle'
    'Melissa Perri + Denise Tilles' → 'melissa-perri-denise-tilles'
    'Gustav Söderström' → 'gustav-soderstrom'
    """
    slug = unicodedata.normalize("NFKD", name)
    slug = "".join(c for c in slug if not unicodedata.combining(c))
    slug = slug.lower().strip()
    slug = slug.replace("+", " ").replace("&", " ").replace("_", " ")
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug


def _normalize_dir(s: str) -> str:
    """Normalize a directory name for fuzzy comparison."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().replace("_", "-")


def already_has_transcript(filename: str) -> bool:
    """Check if we already have this transcript (as .txt or as .md with cache)."""
    stem = filename.rsplit(".", 1)[0]

    # Check if the .txt already exists locally
    if (TRANSCRIPTS_DIR / filename).exists():
        return True

    # Check if an .md version exists via exact slug match
    slug = slugify(stem)
    if (TRANSCRIPTS_DIR / slug / "transcript.md").exists():
        return True

    # Fuzzy match against existing directories
    norm_slug = _normalize_dir(slug)
    for d in TRANSCRIPTS_DIR.iterdir():
        if not d.is_dir():
            continue
        norm_dir = _normalize_dir(d.name)
        if norm_slug == norm_dir:
            return True
        min_len = min(len(norm_slug), len(norm_dir))
        if min_len >= 6 and norm_slug[:min_len] == norm_dir[:min_len]:
            return True

    return False


# ── Main ─────────────────────────────────────────────────────────────────


def main():
    dry_run = "--dry-run" in sys.argv
    token = get_dropbox_token()

    print("Listing files in Dropbox shared folder...")
    dropbox_files = list_dropbox_files(token)
    print(f"Found {len(dropbox_files)} .txt files in Dropbox")

    new_files = []
    for f in dropbox_files:
        name = f["name"]
        if not already_has_transcript(name):
            new_files.append(name)

    if not new_files:
        print("No new transcripts to process.")
        return

    print(f"\n{len(new_files)} new transcript(s) to sync:")
    for name in new_files:
        print(f"  + {name}")

    if dry_run:
        print("\n[DRY RUN] Would download and process the above files.")
        return

    downloaded = []
    for filename in new_files:
        print(f"\nDownloading: {filename}...")
        try:
            content = download_file(token, filename)
            dest = TRANSCRIPTS_DIR / filename
            dest.write_text(content, encoding="utf-8")
            downloaded.append(filename)
            print(f"  Saved: {dest}")
        except Exception as exc:
            print(f"  ERROR downloading {filename}: {exc}")

    if not downloaded:
        print("\nNo files downloaded successfully.")
        return

    print(f"\nRunning indexing pipeline for {len(downloaded)} new episode(s)...")
    cmd = [
        "uv", "run", "python", "-m", "indexer.run",
        "--transcripts", str(TRANSCRIPTS_DIR),
    ]
    result = subprocess.run(cmd, cwd=str(INDEXER_DIR))

    if result.returncode == 0:
        print("\nSync complete.")
    else:
        print(f"\nPipeline exited with code {result.returncode}")


if __name__ == "__main__":
    main()
