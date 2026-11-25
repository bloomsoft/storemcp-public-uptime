"""Unauthenticated external StoreMCP probe; no secrets or customer data required."""
import argparse
import json
import ssl
import urllib.error
import urllib.request

BASE = 'https://vps1.bloomsoft.net'
RESOURCE = BASE + '/shopifyapps/StoreMCPAccess/mcp'
METADATA = BASE + '/.well-known/oauth-protected-resource/shopifyapps/StoreMCPAccess/mcp'
LIMIT = 65536


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


def check(transport=request):
    result = []
    status, _, body = transport(BASE + '/shopifyapps/StoreMCPAccess/')
    if status != 200 or b'StoreMCPAccess' not in body:
        raise ValueError('web_application_unavailable')
    result.append('web_application')
    status, _, body = transport(METADATA)
    if status != 200:
        raise ValueError('oauth_discovery_unavailable')
    try:
        metadata = json.loads(body)
    except (ValueError, UnicodeError):
        raise ValueError('oauth_discovery_invalid') from None
    if not isinstance(metadata, dict) or metadata.get('resource') != RESOURCE or \
            metadata.get('authorization_servers') != [BASE + '/shopifyapps/StoreMCPAccess/oauth']:
        raise ValueError('oauth_discovery_invalid')
    result.append('oauth_discovery')
    payload = json.dumps({'jsonrpc': '2.0', 'id': 'uptime-probe', 'method': 'tools/list'}).encode()
    status, headers, _ = transport(RESOURCE, 'POST', payload)
    if status != 401 or 'Bearer' not in headers.get('WWW-Authenticate', '') or \
            METADATA not in headers.get('WWW-Authenticate', ''):
        raise ValueError('mcp_authentication_boundary_unavailable')
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
    except Exception:
        # Never print response bodies, headers, URLs from exceptions or remote text.
        print(json.dumps({'status': 'external_probe_failed', 'application_changed': False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
