# Twentyfourdle

A daily 24 math game with friend groups, server-timed first solves, shared leaderboards, and a simplicity competition.

## Run locally

Requires Python 3.10 or newer. No packages, API keys, or build step needed.

```sh
python server.py
```

On Windows, `py server.py` also works. Open **http://localhost:8000**. Do not open `public/index.html` directly; the game needs the server.

1. Choose a player name and save the private recovery key.
2. Reveal the four numbers to start the timer.
3. Type or tap an expression that makes 24 using every number exactly once.
4. Create a friend group and copy the invite link.
5. Compare first-solve times and, after finishing, everyone’s solutions.
6. Keep trying simpler expressions without changing your original finish time.

To test friends locally, use a second browser or an incognito window. On the same Wi-Fi, friends can use `http://YOUR-COMPUTER-LAN-IP:8000` while the server runs, if your firewall allows it. A localhost invite only works on your own computer. For friends elsewhere, deploy the server to a shared HTTPS host.

## Rules and scoring

- Same puzzle for everyone, changing at **00:00 UTC** (7 p.m. CDT / 6 p.m. CST).
- 404 distinct, verified solvable multisets using numbers 1–9. A fixed shuffled schedule visits all 404 before repeating. Keep the catalog and shuffle version unchanged to preserve previous puzzle assignments.
- Use each of the four number tiles exactly once. Repeated numbers are separate tiles.
- Allowed: `+`, `-`, `*`, `/`, parentheses, negative intermediate results, and fractions.
- Not allowed: concatenation, powers, factorials, unary negation, extra numbers, or implicit multiplication.
- Exact rational arithmetic checks answers; no `eval()` or floating-point tolerance.
- Every expression uses three binary operations, so a fewest-operations leaderboard would always tie. Instead, **simplicity = 1 per addition/subtraction, 2 per multiplication, 3 per division**. Lower wins; equal scores share a rank.
- An exhaustive subset solver finds the minimum score. Its answer is revealed only after a player solves.
- First-solve time is computed on the server and cannot be reset by refreshing or reopening the page. It includes network round trips and any time away.
- Faster leaderboard shows the first submitted solution; simplicity leaderboard shows each player’s best-scoring solution.
- Group solutions are withheld by the API until the viewer completes that day’s puzzle. Leaderboards refresh every 15 seconds.
- This is an honor-system game for friends, not an anti-cheat or prize competition. Players can inspect public source, use external solvers, or create additional identities.

## Saved players and data

SQLite stores players, attempts, groups, and memberships in `data/game.sqlite3`. Data survives server restarts. Back up the database; keep the entire data directory private and out of Git.

A random HttpOnly session cookie identifies a player. Recovery keys are shown once and stored only as hashes. Restoring a player rotates its session, signing out the previous browser. Invite links grant group membership; share them only with intended friends. Display names are not verified or unique. There is no email collection, social login, or password reset service.

## Hosting

This is a Python server, so **GitHub Pages alone cannot run it**. Host the backend and frontend together on one HTTPS origin with a **persistent disk**. Use a reverse proxy in front of the Python server for TLS, request timeouts, and rate limits. The included server is intended for a small group; harden or replace the HTTP serving layer before broad public traffic.

Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8000` | Listening port |
| `HOST` | `0.0.0.0` | Listening interface |
| `DATABASE_PATH` | `data/game.sqlite3` | Persistent SQLite file |
| `COOKIE_SECURE` | `0` | Set `1` on an HTTPS host |

Preserve the incoming Host header through the reverse proxy. Run one application instance with its attached SQLite disk; do not use an ephemeral filesystem or independent replicas. Configure backups and rate limiting at the proxy. There are no billable third-party dependencies in the app.

An optional Docker setup:

```sh
docker build -t twentyfourdle .
docker run --name twentyfourdle -p 8000:8000 -v twentyfourdle-data:/app/data twentyfourdle
```

Add `-e COOKIE_SECURE=1` when placed behind HTTPS. The Docker image runs as a non-root user.

## Tests

```sh
python -m unittest discover -s tests -v
```

Tests verify the full puzzle catalog, exact fractions, invalid/unsafe expressions, optimal scoring, refresh-safe timers, two-player groups, spoiler protection, identity recovery, cross-origin write protection, and daily rollover.

## Project layout

- `server.py`: HTTP routes, sessions, SQLite storage, access checks.
- `game.py`: daily schedule, safe expression parsing, exact arithmetic, optimal solver.
- `puzzles.json`: 404 solvable puzzles.
- `public/`: responsive frontend, no framework or build step.
- `tests/`: math and multi-player API integration tests.
