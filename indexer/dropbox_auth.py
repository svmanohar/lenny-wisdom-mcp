"""One-time Dropbox OAuth setup to get a refresh token.

Run this once:
    uv run python dropbox_auth.py

It will open your browser to authorize the app, then save the refresh token
to ~/.lenny-wisdom/dropbox_token.json for the sync script to use.
"""

import json
import webbrowser
from pathlib import Path

import httpx

APP_KEY = "k6vfbuyb7bljfsf"
APP_SECRET = "e3fqxn3phf0vpp0"
TOKEN_FILE = Path.home() / ".lenny-wisdom" / "dropbox_token.json"


def main():
    # Step 1: Direct user to authorize
    auth_url = (
        f"https://www.dropbox.com/oauth2/authorize"
        f"?client_id={APP_KEY}"
        f"&response_type=code"
        f"&token_access_type=offline"  # This gives us a refresh token
    )

    print("Opening browser for Dropbox authorization...")
    print(f"\nIf it doesn't open, go to:\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Step 2: Get the authorization code from user
    auth_code = input("Paste the authorization code here: ").strip()

    # Step 3: Exchange code for refresh token
    print("\nExchanging code for tokens...")
    resp = httpx.post(
        "https://api.dropboxapi.com/oauth2/token",
        data={
            "code": auth_code,
            "grant_type": "authorization_code",
            "client_id": APP_KEY,
            "client_secret": APP_SECRET,
        },
    )

    if not resp.is_success:
        print(f"ERROR: {resp.status_code} — {resp.text}")
        return

    data = resp.json()
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        print(f"ERROR: No refresh token in response: {data}")
        return

    # Step 4: Save refresh token
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps({
        "refresh_token": refresh_token,
        "app_key": APP_KEY,
        "app_secret": APP_SECRET,
    }, indent=2))
    TOKEN_FILE.chmod(0o600)  # Owner-only read/write

    print(f"\nRefresh token saved to {TOKEN_FILE}")
    print("The sync script will auto-refresh access tokens from here.")
    print("\nYou can now run: uv run python sync_dropbox.py --dry-run")


if __name__ == "__main__":
    main()
