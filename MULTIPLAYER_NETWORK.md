# Multiplayer Network Setup

Tavern Tales multiplayer is **host-and-connect**: one person runs the backend
(FastAPI + Ollama), the other connects from their browser over the network.

This guide covers two scenarios:
- **LAN** — both players on the same home/office network (default, easiest)
- **Internet** — players in different locations (requires a tunnel)

---

## LAN (same network)

The host runs everything. The guest needs only a browser.

### Host steps

1. Start the backend with LAN binding:
   ```
   start_backend.bat
   ```
   The script runs `uvicorn main:app --reload --host 0.0.0.0 --port 8000`.
   Binding to `0.0.0.0` lets other machines on the same network reach the
   server. (To restrict back to localhost only, change the `--host` flag.)

2. Start the frontend:
   ```
   start_frontend.bat
   ```
   Vite is configured to bind `0.0.0.0` by default. It will print two URLs:
   ```
   ➜  Local:   http://localhost:5173/
   ➜  Network: http://192.168.x.y:5173/
   ```
   The **Network** URL is what the guest needs.

3. Create a multiplayer session in the **Forge Your World** screen by toggling
   "Multiplayer" before saving the campaign. The lobby will show a 6-character
   room code (e.g. `WOLF42`) and the join URL.

4. Share **the join URL** and **the room code** with the guest.

### Guest steps

1. Open the join URL in a browser.
2. Enter the room code in the lobby.
3. Fill in a character name (and optionally character details and preferences).
4. Click **Ready**. When the host also clicks Ready, the campaign begins.

### Firewall

Windows may prompt to allow Python and Node through the firewall the first time
the host starts the servers. Allow access on **Private networks**.

If the guest cannot connect, verify the host can be reached:
- From the guest's machine, try opening `http://<host_ip>:8000/` in a browser.
  You should see `{"status": "Tavern Tales backend is running.", ...}`.
- If that fails, the firewall is blocking inbound. Open ports 8000 (backend)
  and 5173 (frontend) for the Tavern Tales processes.

---

## Internet (different locations)

The backend was not designed to be exposed directly to the public internet.
Use a tunnel that forwards traffic from a public hostname to your local
backend; the tunnel handles TLS and NAT traversal.

### Option 1 — ngrok (free, temporary URL)

1. Install ngrok: <https://ngrok.com/download>.
2. Start the backend as usual (`start_backend.bat`).
3. In another terminal, expose port 8000:
   ```
   ngrok http 8000
   ```
4. ngrok will print a public HTTPS URL such as `https://1a2b3c.ngrok.app`.
5. Share that URL **plus the room code** with the guest. They open the URL in
   their browser, enter the room code, and join.
6. The frontend (Vite) is also reachable through a separate tunnel if you
   want to skip having the guest reach your local Vite server. For most
   setups, hosting the frontend with `npm run build && npm run preview` and
   tunneling **that** port is cleaner.

ngrok URLs change every time you restart the tunnel on the free tier. Use
Cloudflare Tunnel below for a stable URL.

### Option 2 — Cloudflare Tunnel (free, persistent subdomain)

1. Install `cloudflared`: <https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/>.
2. Authenticate: `cloudflared tunnel login`.
3. Create a named tunnel: `cloudflared tunnel create tavern-tales`.
4. Configure routing in `~/.cloudflared/config.yml`:
   ```yaml
   tunnel: tavern-tales
   credentials-file: /home/you/.cloudflared/<tunnel-id>.json
   ingress:
     - hostname: tavern.example.com
       service: http://localhost:8000
     - service: http_status:404
   ```
5. Run: `cloudflared tunnel run tavern-tales`.
6. The guest accesses `https://tavern.example.com/` and joins as normal.

### CORS for tunneled origins

The backend's CORS allows loopback plus RFC1918 private LAN IPs by default.
Tunnel URLs (`*.ngrok.app`, `*.trycloudflare.com`, your own domain) are not
matched by that regex. Set the `TT_EXTRA_CORS_ORIGINS` environment variable
to a comma-separated list before starting the backend if you need to allow
specific origins:

```
set TT_EXTRA_CORS_ORIGINS=https://1a2b3c.ngrok.app,https://tavern.example.com
start_backend.bat
```

(If `TT_EXTRA_CORS_ORIGINS` is not yet wired up in your build, you can edit
`backend/main.py` and add the tunnel URL to the `allow_origins` list.)

---

## Security notes

- **Room codes are the only authentication.** Anyone who knows the code and
  can reach the host's backend can join as the guest.
- For LAN this is fine: trusted home/office network.
- For internet via tunnel: treat room codes like short-lived passwords. Start
  a new session (which generates a new code) instead of reusing old codes.
- The host has full control: they can eject the guest, archive the session,
  or delete it entirely from the lobby UI.
- Player prompts are private even from each other — only the AI's narration
  is visible to both players. The host's full state JSON contains both
  prompts (necessary for the AI), but the API enforces a host-only header
  check on `GET /api/state/{id}` so the guest's browser cannot read it.

---

## Quick reference

| Action | Where |
|--------|-------|
| Create session | Forge Your World → toggle Multiplayer → Save |
| Find your LAN IP | Backend logs / lobby UI / `GET /api/server/info` |
| Find room code | Lobby screen, top-right |
| Join URL | Lobby shows `http://{lan_ip}:5173/?room_code=XXXXXX` |
| Ports to open in firewall | 8000 (backend), 5173 (frontend dev) |
| Eject guest | Lobby or play screen, host-only button |
| Archive session | Lobby/play screen, host-only — keeps campaign on disk |
| Delete session | Lobby/play screen, host-only — destroys campaign too |
