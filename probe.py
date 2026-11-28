"""Unauthenticated external StoreMCP probe; no secrets or customer data required."""
import argparse
import datetime as dt
import json
import ssl
import urllib.error
import urllib.request

BASE = 'https://vps1.bloomsoft.net'
RESOURCE = BASE + '/shopifyapps/StoreMCPAccess/mcp'
METADATA = BASE + '/.well-known/oauth-protected-resource/shopifyapps/StoreMCPAccess/mcp'
LIMIT = 65536


FAILURE_CATEGORIES = frozenset({
    'web_application_unavailable', 'oauth_discovery_unavailable',
    'oauth_discovery_invalid', 'private_monitor_heartbeat_unavailable',
    'mcp_authentication_boundary_unavailable', 'web_application_transport_failure',
    'oauth_discovery_transport_failure', 'private_monitor_heartbeat_transport_failure',
    'mcp_authentication_boundary_transport_failure', 'unexpected_probe_failure',
})


class ProbeFailure(ValueError):
    def __init__(self, category):
        self.category = category if category in FAILURE_CATEGORIES else 'unexpected_probe_failure'
        super().__init__(self.category)


def checked_request(transport, stage, url, method='GET', body=None):
    try:
        return transport(url, method, body)
    except Exception:
        # Never preserve a provider exception or its URL/headers/body.
        raise ProbeFailure(stage + '_transport_failure') from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url, method='GET', body=None):
    headers = {'User-Agent': 'StoreMCP-UptimeProbe/1', 'Accept': 'application/json'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
        # Public, deliberately invalid synthetic credential, never an app token.
        headers['Authorization'] = 'Bearer mcp_' + 'A' * 43
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        response = opener.open(req, timeout=12)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        content = response.read(LIMIT + 1)
        if len(content) > LIMIT:
            raise ValueError('response_too_large')
        return response.code, response.headers, content


def check(transport=request, now=None):
    result = []
    status, _, body = checked_request(transport, 'web_application', BASE + '/shopifyapps/StoreMCPAccess/')
    if status != 200 or b'StoreMCPAccess' not in body:
        raise ProbeFailure('web_application_unavailable')
    result.append('web_application')
    status, _, body = checked_request(transport, 'oauth_discovery', METADATA)
    if status != 200:
        raise ProbeFailure('oauth_discovery_unavailable')
    try:
        metadata = json.loads(body)
    except (ValueError, UnicodeError):
        raise ProbeFailure('oauth_discovery_invalid') from None
    if not isinstance(metadata, dict) or metadata.get('resource') != RESOURCE or \
            metadata.get('authorization_servers') != [BASE + '/shopifyapps/StoreMCPAccess/oauth']:
        raise ProbeFailure('oauth_discovery_invalid')
    result.append('oauth_discovery')
    status, _, body = checked_request(transport, 'private_monitor_heartbeat', BASE + '/shopifyapps/StoreMCPAccess/ops-health.json')
    try:
        heartbeat = json.loads(body)
        checked = dt.datetime.fromisoformat(heartbeat['checkedAtUtc'].replace('Z', '+00:00'))
        age = ((now or dt.datetime.now(dt.timezone.utc)) - checked).total_seconds()
        valid = status == 200 and set(heartbeat) == {'schema', 'status', 'checkedAtUtc'} and \
            heartbeat['schema'] == 1 and heartbeat['status'] == 'healthy' and -60 <= age <= 300
    except (ValueError, TypeError, KeyError):
        valid = False
    if not valid:
        raise ProbeFailure('private_monitor_heartbeat_unavailable')
    result.append('private_monitor_heartbeat')
    payload = json.dumps({'jsonrpc': '2.0', 'id': 'uptime-probe', 'method': 'tools/list'}).encode()
    status, headers, _ = checked_request(transport, 'mcp_authentication_boundary', RESOURCE, 'POST', payload)
    if status != 401 or 'Bearer' not in headers.get('WWW-Authenticate', '') or \
            METADATA not in headers.get('WWW-Authenticate', ''):
        raise ProbeFailure('mcp_authentication_boundary_unavailable')
    result.append('mcp_authentication_boundary')
    return {'status': 'healthy', 'checks': result, 'shopify_tools_executed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulate-failure', action='store_true', help='Fail a manual notification test without changing the application.')
    args = parser.parse_args()
    try:
        if args.simulate_failure:
            print(json.dumps({'status': 'notification_test_failure', 'application_changed': False}))
            return 1
        print(json.dumps(check()))
        return 0
    except Exception as error:
        # Only fixed categories escape; never remote text, bodies, headers or URLs.
        category = error.category if isinstance(error, ProbeFailure) and error.category in FAILURE_CATEGORIES else 'unexpected_probe_failure'
        print(json.dumps({'status': 'external_probe_failed', 'failure_category': category, 'application_changed': False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
