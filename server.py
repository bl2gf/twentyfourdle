"""Twentyfourdle: dependency-free HTTP server with durable SQLite scores."""
import hashlib
import json
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from game import evaluate, puzzle, solve, today

ROOT = Path(__file__).parent
DB_PATH = Path(os.environ.get('DATABASE_PATH', str(ROOT / 'data' / 'game.sqlite3')))
COOKIE_SECURE = os.environ.get('COOKIE_SECURE', '0') == '1'


def database():
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    return connection


def initialize():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with database() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS players (
            id TEXT PRIMARY KEY, name TEXT NOT NULL,
            session_hash TEXT NOT NULL UNIQUE, recovery_hash TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS attempts (
            player TEXT NOT NULL REFERENCES players(id), day TEXT NOT NULL,
            started INTEGER NOT NULL, elapsed INTEGER, first_expression TEXT,
            best_expression TEXT, best_score INTEGER,
            PRIMARY KEY(player, day)
        );
        CREATE TABLE IF NOT EXISTS clubs (id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS members (
            club TEXT NOT NULL REFERENCES clubs(id), player TEXT NOT NULL REFERENCES players(id),
            PRIMARY KEY(club, player)
        );
        CREATE INDEX IF NOT EXISTS idx_members_player ON members(player);
        ''')


def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def now_ms(): return time.time_ns() // 1_000_000


class Handler(BaseHTTPRequestHandler):
    def json_response(self, payload, status=200, cookie=None):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if cookie:
            self.send_header('Set-Cookie', f'tf_session={cookie}; HttpOnly; SameSite=Lax; Path=/; Max-Age=31536000' + ('; Secure' if COOKIE_SECURE else ''))
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def player(self, db):
        cookies = SimpleCookie()
        try: cookies.load(self.headers.get('Cookie', ''))
        except Exception: return None
        token = cookies.get('tf_session')
        return db.execute('SELECT id, name FROM players WHERE session_hash=?', (digest(token.value),)).fetchone() if token else None

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/state':
            try:
                with database() as db:
                    player = self.player(db)
                    self.json_response(self.state(db, player))
            except Exception as error:
                print('State error:', repr(error), flush=True)
                self.json_response({'error': 'Could not load your game. Please try again.'}, 503)
            return
        assets = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css'), '/favicon.svg': ('favicon.svg', 'image/svg+xml')}
        if path not in assets:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        filename, mime = assets[path]
        data = (ROOT / 'public' / filename).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(data)

    def state(self, db, player):
        day = today()
        tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
        state = {'day': day, 'serverNow': now_ms(), 'resetsAt': tomorrow.isoformat() + 'T00:00:00Z', 'player': dict(player) if player else None}
        if not player: return state
        uid = player['id']
        attempt = db.execute('SELECT * FROM attempts WHERE player=? AND day=?', (uid, day)).fetchone()
        state['attempt'] = dict(attempt) if attempt else None
        state['cards'] = puzzle(day) if attempt else None
        solved = attempt and attempt['elapsed'] is not None
        state['optimal'] = solve(tuple(puzzle(day))) if solved else None
        clubs = db.execute('SELECT c.id, c.name FROM clubs c JOIN members m ON c.id=m.club WHERE m.player=? ORDER BY c.name', (uid,)).fetchall()
        state['clubs'] = []
        for club in clubs:
            rows = db.execute('''SELECT p.id, p.name, a.elapsed, a.first_expression, a.best_expression, a.best_score
                FROM members m JOIN players p ON p.id=m.player
                LEFT JOIN attempts a ON a.player=p.id AND a.day=?
                WHERE m.club=? ORDER BY a.elapsed IS NULL, a.elapsed, p.name''', (day, club['id'])).fetchall()
            result = []
            for row in rows:
                entry = dict(row)
                if not solved:
                    entry['first_expression'] = None
                    entry['best_expression'] = None
                result.append(entry)
            state['clubs'].append({**dict(club), 'players': result})
        return state

    def do_POST(self):
        # JSON and same-origin requests prevent cross-site cookie-authenticated writes.
        origin = self.headers.get('Origin')
        if (origin and urlsplit(origin).netloc != self.headers.get('Host')) or not self.headers.get('Content-Type', '').startswith('application/json'):
            self.json_response({'error': 'Request must come from this game.'}, 403)
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096: raise ValueError('Request is too large or empty.')
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict): raise ValueError('Invalid request.')
            path = urlsplit(self.path).path
            with database() as db:
                # Serialize score writes: two tabs cannot replace the first solve time.
                db.execute('BEGIN IMMEDIATE')
                player = self.player(db)
                cookie = None
                recovery = None
                if path == '/api/profile':
                    name = body.get('name', '')
                    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 24: raise ValueError('Choose a name between 1 and 24 characters.')
                    if player:
                        db.execute('UPDATE players SET name=? WHERE id=?', (name.strip(), player['id']))
                    else:
                        cookie = secrets.token_urlsafe(32)
                        recovery = secrets.token_urlsafe(24)
                        uid = secrets.token_urlsafe(16)
                        db.execute('INSERT INTO players VALUES (?,?,?,?)', (uid, name.strip(), digest(cookie), digest(recovery)))
                        player = {'id': uid}
                elif path == '/api/recover':
                    key = body.get('key', '')
                    if not isinstance(key, str): raise ValueError('Enter your player recovery key.')
                    player = db.execute('SELECT id,name FROM players WHERE recovery_hash=?', (digest(key.strip()),)).fetchone()
                    if not player: raise ValueError('That recovery key was not found.')
                    cookie = secrets.token_urlsafe(32)
                    db.execute('UPDATE players SET session_hash=? WHERE id=?', (digest(cookie), player['id']))
                else:
                    if not player:
                        self.json_response({'error': 'Choose a player name first.'}, 401)
                        return
                    uid = player['id']
                    day = today()
                    if path == '/api/start':
                        db.execute('INSERT OR IGNORE INTO attempts(player,day,started) VALUES(?,?,?)', (uid, day, now_ms()))
                    elif path == '/api/submit':
                        if body.get('day') != day: raise ValueError('A new daily puzzle is ready. Refresh to play today’s challenge.')
                        attempt = db.execute('SELECT * FROM attempts WHERE player=? AND day=?', (uid, day)).fetchone()
                        if not attempt: raise ValueError('Start today’s puzzle first.')
                        solution = evaluate(body.get('expression'), puzzle(day))
                        elapsed = max(0, now_ms() - attempt['started'])
                        if attempt['elapsed'] is None:
                            db.execute('UPDATE attempts SET elapsed=?,first_expression=?,best_expression=?,best_score=? WHERE player=? AND day=?', (elapsed, solution['expression'], solution['expression'], solution['score'], uid, day))
                        elif solution['score'] < attempt['best_score']:
                            db.execute('UPDATE attempts SET best_expression=?,best_score=? WHERE player=? AND day=?', (solution['expression'], solution['score'], uid, day))
                    elif path == '/api/clubs':
                        name = body.get('name', '')
                        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 32: raise ValueError('Give your group a name, up to 32 characters.')
                        count = db.execute('SELECT count(*) FROM members WHERE player=?', (uid,)).fetchone()[0]
                        if count >= 20: raise ValueError('You can belong to up to 20 groups.')
                        code = secrets.token_hex(6).upper()
                        db.execute('INSERT INTO clubs VALUES (?,?)', (code, name.strip()))
                        db.execute('INSERT INTO members VALUES (?,?)', (code, uid))
                    elif path == '/api/join':
                        code = body.get('code', '')
                        if not isinstance(code, str): raise ValueError('Enter an invite code.')
                        code = code.strip().upper()
                        club = db.execute('SELECT id FROM clubs WHERE id=?', (code,)).fetchone()
                        if not club: raise ValueError('That invite code was not found. Check it and try again.')
                        count = db.execute('SELECT count(*) FROM members WHERE player=?', (uid,)).fetchone()[0]
                        if count >= 20: raise ValueError('You can belong to up to 20 groups.')
                        db.execute('INSERT OR IGNORE INTO members VALUES (?,?)', (code, uid))
                    else:
                        self.json_response({'error': 'Not found.'}, 404)
                        return
                player = db.execute('SELECT id,name FROM players WHERE id=?', (player['id'],)).fetchone()
                db.commit()
                state = self.state(db, player)
                if recovery: state['recoveryKey'] = recovery
                self.json_response(state, cookie=cookie)
        except (ValueError, TypeError) as error:
            self.json_response({'error': str(error)}, 400)
        except Exception as error:
            print('Write error:', repr(error), flush=True)
            self.json_response({'error': 'Could not save your game. Your input is safe—please try again.'}, 503)

    def log_message(self, fmt, *args):
        # Do not log invite query strings or recovery credentials.
        print('%s %s' % (self.address_string(), fmt % args), flush=True)


if __name__ == '__main__':
    initialize()
    port = int(os.environ.get('PORT', '8000'))
    print(f'Twentyfourdle is ready at http://localhost:{port}', flush=True)
    ThreadingHTTPServer((os.environ.get('HOST', '0.0.0.0'), port), Handler).serve_forever()
