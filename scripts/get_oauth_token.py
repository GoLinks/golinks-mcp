import base64
import hashlib
import http.server
import json
import os
import secrets
import socketserver
import urllib.parse
import webbrowser
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

CLIENT_ID = os.environ.get("CLIENT_ID", "")
ISSUER = os.environ.get("GOLINKS_OAUTH_ISSUER", "https://www.golinks.io")
AUTHORIZATION_ENDPOINT = os.environ.get(
    "GOLINKS_OAUTH_AUTHORIZE_URL",
    "https://app.golinks.io/oauth_authorize.php",
)
TOKEN_ENDPOINT = os.environ.get(
    "GOLINKS_OAUTH_TOKEN_URL",
    "https://api.golinks.io/oauth/token",
)
SCOPES = os.environ.get("SCOPES", "golinks:read golinks:write search:read")
HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "8000"))
REDIRECT_URI = os.environ.get("REDIRECT_URI", f"http://localhost:{PORT}/callback")


@dataclass
class OAuthCallbackResult:
    code: str | None = None
    state: str | None = None
    error: str | None = None
    error_description: str | None = None


def base64_urlencode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def make_pkce_pair() -> tuple[str, str]:
    verifier = base64_urlencode(secrets.token_bytes(32))
    challenge = base64_urlencode(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def make_callback_handler(expected_state: str, result: OAuthCallbackResult):
    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)

            result.code = params.get("code", [None])[0]
            result.state = params.get("state", [None])[0]
            result.error = params.get("error", [None])[0]
            result.error_description = params.get("error_description", [None])[0]

            if result.error:
                message = f"OAuth failed: {result.error} {result.error_description or ''}"
                status = 400
            elif result.state != expected_state:
                message = "OAuth failed: state did not match."
                status = 400
            elif not result.code:
                message = "OAuth failed: no authorization code returned."
                status = 400
            else:
                message = "OAuth complete. You can close this tab and return to the terminal."
                status = 200

            body = f"<html><body><h1>{message}</h1></body></html>".encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:
            return

    return CallbackHandler


def main() -> None:
    if not CLIENT_ID:
        raise SystemExit(
            "Set CLIENT_ID to your registered GoLinks OAuth app client ID.\n"
            "Example: CLIENT_ID='your-client-id' uv run python scripts/get_oauth_token.py"
        )

    code_verifier, code_challenge = make_pkce_pair()
    state = secrets.token_urlsafe(24)
    result = OAuthCallbackResult()

    authorize_params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    authorize_url = f"{AUTHORIZATION_ENDPOINT}?{urllib.parse.urlencode(authorize_params)}"

    print("Opening OAuth authorize URL in your browser...")
    print(authorize_url)
    print(f"\nWaiting for callback on {REDIRECT_URI}\n")

    handler = make_callback_handler(state, result)
    with socketserver.TCPServer((HOST, PORT), handler) as server:
        webbrowser.open(authorize_url)
        server.handle_request()

    if result.error:
        raise SystemExit(f"OAuth error: {result.error} {result.error_description or ''}")
    if result.state != state:
        raise SystemExit("OAuth error: state mismatch")
    if not result.code:
        raise SystemExit("OAuth error: no code returned")

    token_data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": result.code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": code_verifier,
    }

    response = httpx.post(TOKEN_ENDPOINT, data=token_data, timeout=30)
    if response.status_code != 200:
        print("Token exchange failed:")
        print(response.status_code)
        print(response.text)
        raise SystemExit(1)

    token_response = response.json()
    print("Token response:\n")
    print(json.dumps(token_response, indent=2))
    print("\nUse this for local MCP testing:\n")
    print(f"TOKEN='{token_response['access_token']}' uv run python scripts/test_mcp.py")


if __name__ == "__main__":
    main()
