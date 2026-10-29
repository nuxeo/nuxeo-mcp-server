# Nuxeo MCP Authentication Guide

## Local mode: one identity

The server calls Nuxeo as **one identity, fixed at startup**. Every client that
reaches the server acts as that Nuxeo user, over stdio and over HTTP alike, and
Nuxeo enforces that user's ACLs on every call.

This is the `local` mode, set with `NUXEO_MCP_AUTH_MODE`. `local` is the default
and the only supported value; any other value stops the server at startup.

Local mode is single-tenant. It is safe on your own machine or a trusted
network. It is not safe exposed to callers who should not all act as the
configured Nuxeo user.

## Choosing a credential

| Credential | Use it for | Notes |
|---|---|---|
| Basic (`NUXEO_USERNAME` / `NUXEO_PASSWORD`) | Any transport, including the Docker image | The supported configuration for containers. Both variables are required. |
| OAuth2 (`--oauth2` or `NUXEO_AUTH_METHOD=oauth2`) | stdio, from a desktop MCP client | Not supported in containers, see below. |

`NUXEO_AUTH_METHOD` accepts `basic` (default) or `oauth2`; any other value stops
the server at startup.

## Basic authentication

```bash
export NUXEO_URL="http://localhost:8080/nuxeo"
export NUXEO_USERNAME="alice"
export NUXEO_PASSWORD="secret"
nuxeo-mcp
```

- **There is no default identity.** Without both variables the server refuses to
  start.
- At startup the server checks the credentials against `/api/v1/me`. If Nuxeo
  rejects them (HTTP 401 or 403) the server stops, since no restart can fix
  them. If Nuxeo cannot be reached it logs the failure and starts anyway, as
  Nuxeo may still be starting.
- The password never appears in logs or error messages.
- Prefer a regular Nuxeo user over an administrator; see the README's Account
  Privileges section for what each tool needs.
- Basic authentication sends the credentials on every request: use HTTPS to
  reach any Nuxeo that is not on your machine.

## OAuth2 authentication (stdio, desktop only)

OAuth2 signs you in through your browser and keeps the resulting tokens, so you
do not handle a password. It is meant for running the server over stdio from a
desktop MCP client.

**It does not work in a container.** Sign-in opens a browser and waits for the
redirect on a callback server bound to `localhost` inside the server process; in
a container that listener is not reachable from the host's browser. Use Basic
authentication there.

### 1. Register an OAuth2 client in Nuxeo

As an administrator, register a client through the REST API. The redirect URI
must match the callback the server listens on, `http://localhost:<port>/callback`,
so pick a fixed port:

```bash
curl -u Administrator:<password> -H 'Content-Type: application/json' \
  -X POST http://localhost:8080/nuxeo/api/v1/oauth2/client -d '{
    "entity-type": "oauth2Client",
    "id": "nuxeo-mcp",
    "name": "Nuxeo MCP server",
    "secret": "<client secret>",
    "redirectURIs": ["http://localhost:8888/callback"],
    "isAutoGrant": true,
    "isEnabled": true
  }'
```

`GET /api/v1/oauth2/client` lists the registered clients.

### 2. Configure and start

```bash
export NUXEO_URL="http://localhost:8080/nuxeo"
export NUXEO_OAUTH_CLIENT_ID="nuxeo-mcp"
export NUXEO_OAUTH_CLIENT_SECRET="<client secret>"
export NUXEO_OAUTH_REDIRECT_PORT="8888"   # must match the registered redirect URI

nuxeo-mcp --oauth2
# or: NUXEO_AUTH_METHOD=oauth2 nuxeo-mcp
```

Optional variables:

| Variable | Default |
|---|---|
| `NUXEO_OAUTH_REDIRECT_PORT` | a free port picked at startup; set it, or the redirect URI will not match |
| `NUXEO_OAUTH_SCOPE` | `openid profile email` |
| `NUXEO_OAUTH_AUTH_ENDPOINT`, `NUXEO_OAUTH_TOKEN_ENDPOINT` | Nuxeo's own `/oauth2/authorize` and `/oauth2/token` |
| `NUXEO_OAUTH_OPENID_URL` | none; when set, the endpoints are read from this OpenID configuration |

### 3. Sign-in flow

1. At startup the server looks for a stored token for `NUXEO_URL` and checks it
   with Nuxeo. A valid token is reused without a browser.
2. Without one, or if Nuxeo rejects it (HTTP 401 or 403), the server opens your
   browser on the Nuxeo sign-in page, using PKCE, and waits up to 5 minutes for
   the redirect.
3. It exchanges the code for tokens, stores them, and starts. Expired tokens are
   refreshed with the refresh token.
4. If Nuxeo cannot be reached when checking a stored token, the token is kept,
   not discarded.

`/health` reports `auth_method: oauth2` and the signed-in user.

### Token storage

Tokens are kept in the operating system's keyring when one is available
(macOS Keychain, Windows Credential Manager, Linux Secret Service). Otherwise
they go in an encrypted `tokens.enc` file whose key sits beside it, both
readable only by your user. The fallback directory is `nuxeo-mcp/tokens` under
`~/Library/Application Support` on macOS, `$XDG_DATA_HOME` (default
`~/.local/share`) on Linux, and `%APPDATA%` on Windows.

To sign in again from scratch, clear the stored tokens:

```python
from nuxeo_mcp.token_store import TokenManager

TokenManager().delete_token("http://localhost:8080/nuxeo")  # one server
TokenManager().clear_all_tokens()                           # all
```

### Known limitation

`--no-browser` does not prevent the browser from opening: the server signs in
while it is being created, before the flag is read.

## Troubleshooting

**The server stops with "requires NUXEO_USERNAME and NUXEO_PASSWORD".** Basic
authentication has no default identity; set both variables.

**The server stops with "Nuxeo rejected the credentials".** Nuxeo answered 401
or 403 to `/api/v1/me`; fix the username or password.

**OAuth2 sign-in fails after the browser redirect.** Check that the registered
redirect URI is exactly `http://localhost:<NUXEO_OAUTH_REDIRECT_PORT>/callback`
and that the client id and secret match.

**OAuth2 in Docker never completes.** Expected: use Basic authentication in
containers.

**No keyring available.** The encrypted file fallback is used automatically;
check the permissions of the fallback directory above.
