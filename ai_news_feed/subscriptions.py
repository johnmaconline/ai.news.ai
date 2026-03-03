##########################################################################################
#
# Script name: subscriptions.py
#
# Description: Local subscription API service with double opt-in and unsubscribe support.
#
##########################################################################################

import argparse
import hmac
import json
import logging
import os
import secrets
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None


# ****************************************************************************************
# Global data and configuration
# ****************************************************************************************

log = logging.getLogger(os.path.basename(sys.argv[0]))
log.setLevel(logging.DEBUG)
log.propagate = False
formatter = logging.Formatter(
    '%(asctime)-15s [%(funcName)25s:%(lineno)-5s] %(levelname)-8s %(message)s'
)

fh = logging.FileHandler('ai_news_feed.log', mode='a')
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
if not any(isinstance(handler, logging.FileHandler) for handler in log.handlers):
    log.addHandler(fh)

root_log = logging.getLogger()
root_log.setLevel(logging.DEBUG)
if not any(isinstance(handler, logging.FileHandler) for handler in root_log.handlers):
    root_log.addHandler(fh)

DEFAULT_DB_PATH = 'data/subscribers.db'
DEFAULT_CONFIRM_TTL_HOURS = 72
DEFAULT_UNSUBSCRIBE_TTL_HOURS = 24 * 365 * 5
TOKEN_TYPES = {'confirm', 'unsubscribe'}


# ****************************************************************************************
# Functions
# ****************************************************************************************


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(dt: datetime | None = None) -> str:
    value = dt or _utc_now()
    return value.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _parse_iso_utc(value: str) -> datetime:
    return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _token_secret() -> str:
    return (os.getenv('SUBSCRIPTION_TOKEN_SECRET') or '').strip() or 'dev-insecure-token-secret'


def _normalize_email(value: str) -> str:
    cleaned = (value or '').strip().lower()
    if '@' not in cleaned:
        return ''
    local, _, domain = cleaned.partition('@')
    if not local or '.' not in domain or ' ' in cleaned:
        return ''
    return cleaned


def _hash_token(token: str) -> str:
    secret = _token_secret().encode('utf-8')
    return hmac.new(secret, token.encode('utf-8'), 'sha256').hexdigest()


def _sqlite_connection(db_path: str) -> sqlite3.Connection:
    _ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_subscriptions_db(db_path: str) -> None:
    with _sqlite_connection(db_path) as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS subscribers (
                email TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                source TEXT,
                created_at TEXT NOT NULL,
                confirmed_at TEXT,
                unsubscribed_at TEXT,
                updated_at TEXT NOT NULL
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS subscription_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                token_type TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                FOREIGN KEY(email) REFERENCES subscribers(email)
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_tokens_lookup ON subscription_tokens(token_hash, token_type)'
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS subscription_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                event_type TEXT NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL
            )
            '''
        )
        conn.commit()


def _record_event(conn: sqlite3.Connection, email: str, event_type: str, detail: str) -> None:
    conn.execute(
        '''
        INSERT INTO subscription_events(email, event_type, detail, created_at)
        VALUES(?, ?, ?, ?)
        ''',
        (email, event_type, detail, _iso_utc()),
    )


def _upsert_subscriber_pending(conn: sqlite3.Connection, email: str, source: str) -> str:
    row = conn.execute('SELECT status FROM subscribers WHERE email = ?', (email,)).fetchone()
    now = _iso_utc()
    if row is None:
        conn.execute(
            '''
            INSERT INTO subscribers(email, status, source, created_at, confirmed_at, unsubscribed_at, updated_at)
            VALUES(?, ?, ?, ?, NULL, NULL, ?)
            ''',
            (email, 'pending', source, now, now),
        )
        _record_event(conn, email, 'subscribed_pending', f'source={source}')
        return 'pending'
    if row['status'] == 'active':
        _record_event(conn, email, 'subscribe_repeat_active', f'source={source}')
        return 'active'
    conn.execute(
        '''
        UPDATE subscribers
        SET status = ?, source = ?, unsubscribed_at = NULL, updated_at = ?
        WHERE email = ?
        ''',
        ('pending', source, now, email),
    )
    _record_event(conn, email, 'subscribed_pending', f'source={source}')
    return 'pending'


def _create_token(
    conn: sqlite3.Connection,
    email: str,
    token_type: str,
    ttl_hours: int,
) -> str:
    if token_type not in TOKEN_TYPES:
        raise ValueError(f'Unsupported token type: {token_type}')
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    now = _utc_now()
    expires_at = now + timedelta(hours=ttl_hours)
    conn.execute(
        '''
        INSERT INTO subscription_tokens(email, token_type, token_hash, created_at, expires_at, used_at)
        VALUES(?, ?, ?, ?, ?, NULL)
        ''',
        (email, token_type, token_hash, _iso_utc(now), _iso_utc(expires_at)),
    )
    return token


def _consume_token(conn: sqlite3.Connection, token: str, token_type: str) -> sqlite3.Row | None:
    token_hash = _hash_token(token)
    row = conn.execute(
        '''
        SELECT id, email, token_type, expires_at, used_at
        FROM subscription_tokens
        WHERE token_hash = ? AND token_type = ?
        ''',
        (token_hash, token_type),
    ).fetchone()
    if row is None:
        return None
    if row['used_at']:
        return None
    expires_at = _parse_iso_utc(row['expires_at'])
    if expires_at < _utc_now():
        return None
    conn.execute(
        'UPDATE subscription_tokens SET used_at = ? WHERE id = ?',
        (_iso_utc(), row['id']),
    )
    return row


def _build_action_url(action: str, token: str, public_base_url: str | None = None) -> str:
    base = (public_base_url or os.getenv('SUBSCRIPTION_PUBLIC_BASE_URL') or '').strip()
    if not base:
        base = 'http://localhost:8090'
    base = base.rstrip('/')
    return f'{base}/{action}?{urlencode({"token": token})}'


def _send_email_via_resend(to_email: str, subject: str, html: str, text: str) -> bool:
    if requests is None:
        return False
    api_key = (os.getenv('RESEND_API_KEY') or '').strip()
    from_email = (os.getenv('NEWSLETTER_FROM_EMAIL') or '').strip()
    if not api_key or not from_email:
        log.warning('Email send skipped: RESEND_API_KEY or NEWSLETTER_FROM_EMAIL missing.')
        return False
    payload = {
        'from': from_email,
        'to': [to_email],
        'subject': subject,
        'html': html,
        'text': text,
    }
    reply_to = (os.getenv('NEWSLETTER_REPLY_TO') or '').strip()
    if reply_to:
        payload['reply_to'] = reply_to
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    response = requests.post(
        'https://api.resend.com/emails',
        headers=headers,
        json=payload,
        timeout=20,
    )
    if response.status_code >= 400:
        log.warning('Resend request failed (%s): %s', response.status_code, response.text[:240])
        return False
    return True


def _send_confirmation_email(email: str, confirm_url: str) -> bool:
    subject = 'Confirm your Daily AI Feed subscription'
    html = (
        '<p>Confirm your Daily AI Feed subscription.</p>'
        f'<p><a href="{confirm_url}">Confirm subscription</a></p>'
        '<p>If you did not request this, you can ignore this email.</p>'
    )
    text = (
        'Confirm your Daily AI Feed subscription.\n\n'
        f'Confirm subscription: {confirm_url}\n\n'
        'If you did not request this, you can ignore this email.\n'
    )
    return _send_email_via_resend(email, subject, html, text)


def _send_subscribed_email(email: str, unsubscribe_url: str) -> bool:
    subject = 'You are subscribed to Daily AI Feed'
    html = (
        '<p>You are now subscribed to Daily AI Feed.</p>'
        f'<p>If needed, you can unsubscribe here: <a href="{unsubscribe_url}">Unsubscribe</a></p>'
    )
    text = (
        'You are now subscribed to Daily AI Feed.\n\n'
        f'Unsubscribe: {unsubscribe_url}\n'
    )
    return _send_email_via_resend(email, subject, html, text)


def subscribe_email(
    db_path: str,
    email: str,
    source: str = 'site',
    public_base_url: str | None = None,
) -> dict:
    normalized_email = _normalize_email(email)
    if not normalized_email:
        return {'ok': False, 'error': 'invalid_email'}
    init_subscriptions_db(db_path)
    with _sqlite_connection(db_path) as conn:
        status = _upsert_subscriber_pending(conn, normalized_email, source)
        if status == 'active':
            conn.commit()
            return {'ok': True, 'status': 'already_active'}
        token = _create_token(
            conn,
            email=normalized_email,
            token_type='confirm',
            ttl_hours=DEFAULT_CONFIRM_TTL_HOURS,
        )
        conn.commit()
    confirm_url = _build_action_url('confirm', token, public_base_url=public_base_url)
    email_sent = _send_confirmation_email(normalized_email, confirm_url)
    return {
        'ok': True,
        'status': 'pending_confirmation',
        'email_sent': email_sent,
        'confirm_url': confirm_url,
    }


def confirm_subscription(db_path: str, token: str, public_base_url: str | None = None) -> dict:
    token_value = (token or '').strip()
    if not token_value:
        return {'ok': False, 'error': 'missing_token'}
    init_subscriptions_db(db_path)
    with _sqlite_connection(db_path) as conn:
        row = _consume_token(conn, token_value, 'confirm')
        if row is None:
            conn.commit()
            return {'ok': False, 'error': 'invalid_or_expired_token'}
        email = row['email']
        now = _iso_utc()
        conn.execute(
            '''
            UPDATE subscribers
            SET status = ?, confirmed_at = ?, updated_at = ?
            WHERE email = ?
            ''',
            ('active', now, now, email),
        )
        _record_event(conn, email, 'confirmed', '')
        unsubscribe_token = _create_token(
            conn,
            email=email,
            token_type='unsubscribe',
            ttl_hours=DEFAULT_UNSUBSCRIBE_TTL_HOURS,
        )
        conn.commit()
    unsubscribe_url = _build_action_url('unsubscribe', unsubscribe_token, public_base_url=public_base_url)
    _send_subscribed_email(email, unsubscribe_url)
    return {'ok': True, 'status': 'active', 'email': email, 'unsubscribe_url': unsubscribe_url}


def unsubscribe_subscription(db_path: str, token: str) -> dict:
    token_value = (token or '').strip()
    if not token_value:
        return {'ok': False, 'error': 'missing_token'}
    init_subscriptions_db(db_path)
    with _sqlite_connection(db_path) as conn:
        row = _consume_token(conn, token_value, 'unsubscribe')
        if row is None:
            conn.commit()
            return {'ok': False, 'error': 'invalid_or_expired_token'}
        email = row['email']
        now = _iso_utc()
        conn.execute(
            '''
            UPDATE subscribers
            SET status = ?, unsubscribed_at = ?, updated_at = ?
            WHERE email = ?
            ''',
            ('unsubscribed', now, now, email),
        )
        _record_event(conn, email, 'unsubscribed', '')
        conn.commit()
    return {'ok': True, 'status': 'unsubscribed', 'email': email}


def _response_html(title: str, message: str) -> str:
    safe_title = title.replace('<', '').replace('>', '')
    safe_message = message.replace('<', '').replace('>', '')
    return (
        '<!doctype html>'
        '<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{safe_title}</title>'
        '<style>body{font-family:Arial,sans-serif;max-width:640px;margin:48px auto;padding:0 16px;line-height:1.4;}'
        'h1{font-size:1.4rem;}p{color:#333;}</style></head><body>'
        f'<h1>{safe_title}</h1><p>{safe_message}</p></body></html>'
    )


def _cors_origins() -> list[str]:
    raw = (os.getenv('NEWSLETTER_CORS_ORIGINS') or '').strip()
    if not raw:
        return ['*']
    return [part.strip() for part in raw.split(',') if part.strip()]


def _allowed_origin(request_origin: str) -> str:
    allowed = _cors_origins()
    if '*' in allowed:
        return '*'
    if request_origin in allowed:
        return request_origin
    return allowed[0] if allowed else '*'


class SubscriptionRequestHandler(BaseHTTPRequestHandler):
    db_path = DEFAULT_DB_PATH

    def _request_base_url(self) -> str:
        forwarded_proto = (self.headers.get('X-Forwarded-Proto') or '').strip()
        forwarded_host = (self.headers.get('X-Forwarded-Host') or '').strip()
        host = forwarded_host or (self.headers.get('Host') or f'localhost:{self.server.server_port}')
        proto = forwarded_proto or 'http'
        return f'{proto}://{host}'

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode('utf-8')
        request_origin = (self.headers.get('Origin') or '').strip()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', _allowed_origin(request_origin))
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status: int = 200) -> None:
        body = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_payload(self) -> dict:
        content_length = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(content_length) if content_length > 0 else b''
        content_type = (self.headers.get('Content-Type') or '').lower()
        if 'application/json' in content_type:
            try:
                payload = json.loads(raw.decode('utf-8') or '{}')
            except json.JSONDecodeError:
                return {}
            if isinstance(payload, dict):
                return payload
            return {}
        parsed = parse_qs(raw.decode('utf-8'))
        return {key: (values[0] if values else '') for key, values in parsed.items()}

    def do_OPTIONS(self) -> None:  # noqa: N802
        request_origin = (self.headers.get('Origin') or '').strip()
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header('Access-Control-Allow-Origin', _allowed_origin(request_origin))
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == '/health':
            self._send_json({'ok': True, 'service': 'subscriptions'})
            return
        query = parse_qs(parsed.query or '')
        token = (query.get('token') or [''])[0]
        if parsed.path == '/confirm':
            result = confirm_subscription(
                db_path=self.db_path,
                token=token,
                public_base_url=self._request_base_url(),
            )
            if result.get('ok'):
                self._send_html(_response_html('Subscription confirmed', 'You are subscribed to Daily AI Feed.'))
            else:
                self._send_html(
                    _response_html('Confirmation failed', 'This confirmation link is invalid or expired.'),
                    status=HTTPStatus.BAD_REQUEST,
                )
            return
        if parsed.path == '/unsubscribe':
            result = unsubscribe_subscription(db_path=self.db_path, token=token)
            if result.get('ok'):
                self._send_html(_response_html('Unsubscribed', 'You have been unsubscribed.'))
            else:
                self._send_html(
                    _response_html('Unsubscribe failed', 'This unsubscribe link is invalid or expired.'),
                    status=HTTPStatus.BAD_REQUEST,
                )
            return
        self._send_json({'ok': False, 'error': 'not_found'}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != '/subscribe':
            self._send_json({'ok': False, 'error': 'not_found'}, status=HTTPStatus.NOT_FOUND)
            return
        payload = self._read_payload()
        email = (payload.get('email') or '').strip()
        source = (payload.get('source') or 'site').strip()
        honeypot = (payload.get('company') or payload.get('website') or '').strip()
        if honeypot:
            self._send_json(
                {
                    'ok': True,
                    'status': 'pending_confirmation',
                    'message': 'Check your inbox to confirm your subscription.',
                }
            )
            return
        result = subscribe_email(
            db_path=self.db_path,
            email=email,
            source=source,
            public_base_url=self._request_base_url(),
        )
        if not result.get('ok'):
            self._send_json(
                {'ok': False, 'error': result.get('error', 'invalid_request')},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        self._send_json(
            {
                'ok': True,
                'status': result.get('status'),
                'message': 'Check your inbox to confirm your subscription.',
            }
        )


def run_server(db_path: str, host: str, port: int) -> None:
    init_subscriptions_db(db_path)
    SubscriptionRequestHandler.db_path = db_path
    httpd = ThreadingHTTPServer((host, port), SubscriptionRequestHandler)
    log.info('Subscription service listening on http://%s:%s', host, port)
    httpd.serve_forever()


# ****************************************************************************************
# Handle the arguments
# ****************************************************************************************


def handle_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run Daily AI Feed subscription service.')
    parser.add_argument('--db-path', default=os.getenv('SUBSCRIPTION_DB_PATH') or DEFAULT_DB_PATH)
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8090)
    parser.add_argument('--init-db', action='store_true')
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output to stdout.')
    parser.add_argument('-q', '--quiet', action='store_true', help='Minimal stdout.')
    args = parser.parse_args()

    ch = logging.StreamHandler(sys.stdout)
    if args.verbose:
        ch.setLevel(logging.DEBUG)
    elif args.quiet:
        ch.setLevel(logging.ERROR)
    else:
        ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    log.addHandler(ch)
    root_log.addHandler(ch)

    log.debug('Checking script requirements...')
    if not args.verbose and not args.quiet:
        log.debug('No output level specified. Defaulting to INFO.')

    log.info('++++++++++++++++++++++++++++++++++++++++++++++')
    log.info('+  %s', os.path.basename(sys.argv[0]))
    log.info('+  Python Version: %s', sys.version.split()[0])
    log.info('+  Today is: %s', date.today())
    log.info('++++++++++++++++++++++++++++++++++++++++++++++')
    return args


# ****************************************************************************************
# Main
# ****************************************************************************************


def main() -> None:
    args = handle_args()
    if args.init_db:
        init_subscriptions_db(args.db_path)
        log.info('Initialized subscription database at %s', args.db_path)
    if args.serve:
        run_server(db_path=args.db_path, host=args.host, port=args.port)
        return
    if not args.init_db:
        log.info('No action specified. Use --serve and/or --init-db.')


if __name__ == '__main__':
    main()
