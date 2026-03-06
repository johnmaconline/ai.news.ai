##########################################################################################
#
# Script name: discord_setup.py
#
# Description: Bootstrap Discord bot setup for Daily AI Feed ingestion.
#
##########################################################################################

import argparse
import logging
import os
import sys
import webbrowser
from datetime import date
from urllib.parse import urlencode

try:
    import requests
except Exception:  # noqa: BLE001
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
root_log.setLevel(logging.INFO)
if not any(isinstance(handler, logging.FileHandler) for handler in root_log.handlers):
    root_log.addHandler(fh)

DISCORD_API_BASE = 'https://discord.com/api/v10'
DEFAULT_BOT_PERMISSIONS = 66560  # VIEW_CHANNEL + READ_MESSAGE_HISTORY
DEFAULT_SCOPES = 'bot,applications.commands'
SUPPORTED_CHANNEL_TYPES = {
    0: 'text',
    5: 'announcement',
    15: 'forum',
}


# ****************************************************************************************
# Exceptions
# ****************************************************************************************


class Error(Exception):
    '''
    Base class for exceptions in this module.
    '''


class RequestError(Error):
    '''
    Raised when Discord API request fails.
    '''

    def __init__(self, method: str, url: str, status_code: int, body: str) -> None:
        snippet = body.strip().replace('\n', ' ')[:220]
        message = f'{method} {url} failed ({status_code}): {snippet}'
        super().__init__(message)


# ****************************************************************************************
# Functions
# ****************************************************************************************


def _parse_scopes(scopes_raw: str) -> str:
    scopes = [value.strip() for value in scopes_raw.replace(' ', ',').split(',') if value.strip()]
    deduped: list[str] = []
    seen: set[str] = set()
    for scope in scopes:
        if scope in seen:
            continue
        seen.add(scope)
        deduped.append(scope)
    return ' '.join(deduped)


def _discord_get(
    path: str,
    bot_token: str,
    timeout_seconds: int,
    params: dict | None = None,
) -> dict | list:
    if requests is None:
        raise SystemExit('requests is not installed. Run: pip install -r requirements.txt')
    url = f'{DISCORD_API_BASE}{path}'
    headers = {
        'Authorization': f'Bot {bot_token}',
        'User-Agent': 'daily-ai-feed/discord-setup',
    }
    try:
        response = requests.get(url, headers=headers, params=params, timeout=timeout_seconds)
    except requests.RequestException as exc:
        raise RequestError('GET', url, -1, str(exc)) from exc
    if response.status_code >= 400:
        raise RequestError('GET', url, response.status_code, response.text or '')
    try:
        return response.json()
    except ValueError:
        raise RequestError('GET', url, response.status_code, 'Invalid JSON response')


def build_install_url(
    application_id: str,
    scopes_raw: str,
    permissions: int,
    guild_id: str | None = None,
) -> str:
    params = {
        'client_id': application_id,
        'scope': _parse_scopes(scopes_raw),
        'permissions': str(permissions),
    }
    if guild_id:
        params['guild_id'] = guild_id
        params['disable_guild_select'] = 'true'
    return f'https://discord.com/oauth2/authorize?{urlencode(params)}'


def get_bot_identity(bot_token: str, timeout_seconds: int) -> dict:
    payload = _discord_get('/users/@me', bot_token=bot_token, timeout_seconds=timeout_seconds)
    if not isinstance(payload, dict):
        raise RequestError('GET', f'{DISCORD_API_BASE}/users/@me', 200, 'Unexpected payload shape')
    return payload


def get_bot_guilds(bot_token: str, timeout_seconds: int) -> list[dict]:
    payload = _discord_get('/users/@me/guilds', bot_token=bot_token, timeout_seconds=timeout_seconds)
    if not isinstance(payload, list):
        raise RequestError('GET', f'{DISCORD_API_BASE}/users/@me/guilds', 200, 'Unexpected payload shape')
    rows: list[dict] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        guild_id = str(row.get('id') or '').strip()
        name = str(row.get('name') or '').strip()
        if not guild_id:
            continue
        rows.append(
            {
                'id': guild_id,
                'name': name or f'guild-{guild_id}',
            }
        )
    return rows


def get_guild_channels(guild_id: str, bot_token: str, timeout_seconds: int) -> list[dict]:
    payload = _discord_get(
        f'/guilds/{guild_id}/channels',
        bot_token=bot_token,
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(payload, list):
        raise RequestError(
            'GET',
            f'{DISCORD_API_BASE}/guilds/{guild_id}/channels',
            200,
            'Unexpected payload shape',
        )

    rows: list[dict] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        channel_type = int(row.get('type') or -1)
        if channel_type not in SUPPORTED_CHANNEL_TYPES:
            continue
        channel_id = str(row.get('id') or '').strip()
        channel_name = str(row.get('name') or '').strip()
        if not channel_id or not channel_name:
            continue
        rows.append(
            {
                'id': channel_id,
                'name': channel_name,
                'type': SUPPORTED_CHANNEL_TYPES[channel_type],
                'position': int(row.get('position') or 0),
            }
        )
    rows.sort(key=lambda item: (item['position'], item['name'].lower()))
    return rows


def _parse_csv_ids(value: str | None) -> list[str]:
    if not value:
        return []
    return [entry.strip() for entry in value.split(',') if entry.strip()]


def _redact_token(value: str) -> str:
    if not value:
        return '<missing>'
    if len(value) <= 8:
        return '*' * len(value)
    return f'{value[:4]}...{value[-4:]}'


def _upsert_env_values(env_path: str, values: dict[str, str]) -> int:
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as handle:
            lines = handle.read().splitlines()
    else:
        lines = []

    index_by_key: dict[str, int] = {}
    for idx, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        key = stripped.split('=', 1)[0].strip()
        if key:
            index_by_key[key] = idx

    update_count = 0
    for key, value in values.items():
        if value is None:
            continue
        clean_value = str(value).replace('\n', '').replace('\r', '')
        new_line = f'{key}={clean_value}'
        if key in index_by_key:
            existing_idx = index_by_key[key]
            if lines[existing_idx] != new_line:
                lines[existing_idx] = new_line
                update_count += 1
        else:
            lines.append(new_line)
            update_count += 1

    if update_count > 0:
        with open(env_path, 'w', encoding='utf-8') as handle:
            handle.write('\n'.join(lines).rstrip() + '\n')
    return update_count


def _append_feeds_other(feeds_file: str, lines_to_add: list[str]) -> int:
    if not lines_to_add:
        return 0
    if os.path.exists(feeds_file):
        with open(feeds_file, 'r', encoding='utf-8') as handle:
            lines = handle.read().splitlines()
    else:
        lines = [
            '# Feed Registry',
            '',
            '## 1. URLs',
            '',
            '## 2. LinkedIN users',
            '',
            '## 3. X users',
            '',
            '## 4. other',
            '',
        ]

    other_header_idx: int | None = None
    next_header_idx: int | None = None
    for idx, raw_line in enumerate(lines):
        stripped = raw_line.strip().lower()
        if stripped.startswith('##') and 'other' in stripped:
            other_header_idx = idx
            continue
        if other_header_idx is not None and stripped.startswith('##'):
            next_header_idx = idx
            break

    if other_header_idx is None:
        lines.extend(['', '## 4. other', ''])
        other_header_idx = len(lines) - 2

    existing = {raw.strip() for raw in lines if raw.strip().startswith('- ')}
    deduped_to_add = [line for line in lines_to_add if line.strip() and line.strip() not in existing]
    if not deduped_to_add:
        return 0

    insert_idx = next_header_idx if next_header_idx is not None else len(lines)
    if insert_idx > 0 and lines[insert_idx - 1].strip():
        lines.insert(insert_idx, '')
        insert_idx += 1

    for row in deduped_to_add:
        lines.insert(insert_idx, row)
        insert_idx += 1

    with open(feeds_file, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines).rstrip() + '\n')
    return len(deduped_to_add)


def _build_feeds_other_rows(guild_id: str, channels: list[dict]) -> list[str]:
    rows: list[str] = []
    for channel in channels:
        rows.append(
            f'- discord://guild/{guild_id}/channel/{channel["id"]} '
            f'| name=Discord #{channel["name"]} '
            '| section=under-the-radar '
            '| tags=discord,social,under-the-radar'
        )
    return rows


# ****************************************************************************************
# Handle the arguments
# ****************************************************************************************


def handle_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Discord setup utility for Daily AI Feed.')
    parser.add_argument('--application-id', default=os.getenv('DISCORD_APPLICATION_ID', '').strip())
    parser.add_argument('--bot-token', default=os.getenv('DISCORD_BOT_TOKEN', '').strip())
    parser.add_argument('--guild-id', default=os.getenv('DISCORD_GUILD_ID', '').strip())
    parser.add_argument(
        '--permissions',
        type=int,
        default=int(os.getenv('DISCORD_BOT_PERMISSIONS', str(DEFAULT_BOT_PERMISSIONS))),
        help='Discord permission bitset (default is read-only channel history).',
    )
    parser.add_argument(
        '--scopes',
        default=os.getenv('DISCORD_BOT_SCOPES', DEFAULT_SCOPES),
        help='Comma-separated or space-separated OAuth scopes.',
    )
    parser.add_argument(
        '--channel-ids',
        default=os.getenv('DISCORD_CHANNEL_IDS', '').strip(),
        help='Comma-separated channel IDs to pin.',
    )
    parser.add_argument(
        '--channel-name-contains',
        default='',
        help='Optional case-insensitive filter for channel names.',
    )
    parser.add_argument('--channel-limit', type=int, default=10)
    parser.add_argument('--timeout-seconds', type=int, default=20)
    parser.add_argument('--open-install-url', action='store_true')
    parser.add_argument('--write-env', default='', help='Path to .env file to update.')
    parser.add_argument('--feeds-file', default='config/feeds.md')
    parser.add_argument('--append-feeds-other', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output to stdout.')
    parser.add_argument('-q', '--quiet', action='store_true', help='Minimal stdout.')
    args = parser.parse_args()

    ch = logging.StreamHandler(sys.stdout)
    if args.verbose:
        ch.setLevel(logging.DEBUG)
        root_log.setLevel(logging.DEBUG)
    elif args.quiet:
        ch.setLevel(logging.ERROR)
        root_log.setLevel(logging.ERROR)
    else:
        ch.setLevel(logging.INFO)
        root_log.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    log.addHandler(ch)
    root_log.addHandler(ch)

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

    if not args.application_id:
        raise SystemExit('Missing application id. Set --application-id or DISCORD_APPLICATION_ID.')

    install_url = build_install_url(
        application_id=args.application_id,
        scopes_raw=args.scopes,
        permissions=args.permissions,
        guild_id=(args.guild_id or None),
    )
    log.info('Discord bot install URL:')
    log.info('%s', install_url)
    if args.open_install_url:
        webbrowser.open(install_url)

    if not args.bot_token:
        log.warning('No bot token provided. Set --bot-token or DISCORD_BOT_TOKEN to continue API checks.')
        return

    identity = get_bot_identity(args.bot_token, timeout_seconds=max(5, args.timeout_seconds))
    bot_name = str(identity.get('username') or 'unknown-bot')
    bot_id = str(identity.get('id') or '')
    log.info('Bot auth OK: %s (%s), token=%s', bot_name, bot_id, _redact_token(args.bot_token))

    guilds = get_bot_guilds(args.bot_token, timeout_seconds=max(5, args.timeout_seconds))
    if not guilds:
        log.warning(
            'Bot is not in any servers yet. Use install URL, add bot to a server, and rerun this script.'
        )
        return

    log.info('Bot can access %s guild(s):', len(guilds))
    for guild in guilds:
        log.info('- %s | %s', guild['id'], guild['name'])

    guild_id = args.guild_id.strip()
    if not guild_id and len(guilds) == 1:
        guild_id = guilds[0]['id']
        log.info('Using only available guild id: %s', guild_id)

    if not guild_id:
        log.info('No guild selected. Re-run with --guild-id to discover channels and finalize config.')
        return

    channels = get_guild_channels(guild_id, args.bot_token, timeout_seconds=max(5, args.timeout_seconds))
    if args.channel_name_contains.strip():
        needle = args.channel_name_contains.strip().lower()
        channels = [row for row in channels if needle in row['name'].lower()]

    if not channels:
        log.warning('No supported text/forum channels found for guild_id=%s.', guild_id)
        return

    selected_channel_ids = _parse_csv_ids(args.channel_ids)
    selected_channels: list[dict] = []
    if selected_channel_ids:
        by_id = {row['id']: row for row in channels}
        for channel_id in selected_channel_ids:
            if channel_id in by_id:
                selected_channels.append(by_id[channel_id])
    else:
        selected_channels = channels[: max(1, args.channel_limit)]

    log.info('Selected %s channel(s):', len(selected_channels))
    for channel in selected_channels:
        log.info('- %s | #%s | type=%s', channel['id'], channel['name'], channel['type'])

    env_values = {
        'DISCORD_APPLICATION_ID': args.application_id,
        'DISCORD_BOT_TOKEN': args.bot_token,
        'DISCORD_GUILD_ID': guild_id,
        'DISCORD_CHANNEL_IDS': ','.join([channel['id'] for channel in selected_channels]),
        'DISCORD_BOT_SCOPES': args.scopes,
        'DISCORD_BOT_PERMISSIONS': str(args.permissions),
    }
    log.info('Suggested .env values:')
    log.info('DISCORD_APPLICATION_ID=%s', env_values['DISCORD_APPLICATION_ID'])
    log.info('DISCORD_BOT_TOKEN=%s', _redact_token(env_values['DISCORD_BOT_TOKEN']))
    log.info('DISCORD_GUILD_ID=%s', env_values['DISCORD_GUILD_ID'])
    log.info('DISCORD_CHANNEL_IDS=%s', env_values['DISCORD_CHANNEL_IDS'])
    log.info('DISCORD_BOT_SCOPES=%s', env_values['DISCORD_BOT_SCOPES'])
    log.info('DISCORD_BOT_PERMISSIONS=%s', env_values['DISCORD_BOT_PERMISSIONS'])

    if args.write_env.strip():
        updated = _upsert_env_values(args.write_env.strip(), env_values)
        log.info('Updated %s key(s) in %s', updated, args.write_env.strip())

    if args.append_feeds_other:
        feed_rows = _build_feeds_other_rows(guild_id, selected_channels)
        inserted = _append_feeds_other(args.feeds_file, feed_rows)
        log.info('Appended %s Discord note row(s) to %s', inserted, args.feeds_file)


if __name__ == '__main__':
    main()
