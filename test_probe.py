import io
import datetime as dt
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
import probe


def healthy(url, method='GET', body=None):
    if url.endswith('/ops-health.json'):
        return 200, {}, json.dumps({'schema': 1, 'status': 'healthy', 'checkedAtUtc': dt.datetime.now(dt.timezone.utc).isoformat()}).encode()
    if url == probe.METADATA:
        return 200, {}, json.dumps({'resource': probe.RESOURCE, 'authorization_servers': [probe.BASE + '/shopifyapps/StoreMCPAccess/oauth']}).encode()
    if method == 'POST':
        return 401, {'WWW-Authenticate': 'Bearer resource_metadata="' + probe.METADATA + '"'}, b''
    return 200, {}, b'<h1>StoreMCPAccess</h1>'


class ProbeTests(unittest.TestCase):
    def test_healthy_application_discovery_and_authentication_boundary(self):
        self.assertEqual(len(probe.check(healthy)['checks']), 4)

    def test_unhealthy_stale_future_and_unavailable_heartbeat_rejected(self):
        now = dt.datetime.now(dt.timezone.utc)
        for code, state, checked in [(200, 'degraded', now), (503, 'healthy', now),
            (200, 'healthy', now-dt.timedelta(minutes=6)), (200, 'healthy', now+dt.timedelta(minutes=2))]:
            def transport(url, method='GET', body=None):
                if url.endswith('/ops-health.json'):
                    return code, {}, json.dumps({'schema': 1, 'status': state, 'checkedAtUtc': checked.isoformat()}).encode()
                return healthy(url, method, body)
            with self.assertRaises(ValueError): probe.check(transport, now)

    def test_proxy_success_login_redirect_wrong_resource_and_auth_failure_do_not_pass(self):
        for target, status, headers, content in [
            ('web', 302, {}, b''), ('web', 200, {}, b'proxy placeholder'),
            ('metadata', 200, {}, b'{"resource":"https://wrong.example"}'),
            ('metadata', 503, {}, b'private error'), ('auth', 200, {}, b'{}'),
            ('auth', 401, {'WWW-Authenticate': 'Basic'}, b''), ('auth', 500, {}, b'private error')]:
            def transport(url, method='GET', body=None):
                kind = 'auth' if method == 'POST' else 'metadata' if url == probe.METADATA else 'web'
                return (status, headers, content) if kind == target else healthy(url, method, body)
            with self.subTest(target=target, status=status), self.assertRaises(ValueError):
                probe.check(transport)

    def test_failures_never_print_raw_remote_details(self):
        out = io.StringIO()
        with patch('sys.argv', ['probe']), patch.object(probe, 'check', side_effect=RuntimeError('private-token-or-error')), redirect_stdout(out):
            self.assertEqual(probe.main(), 1)
        self.assertNotIn('private', out.getvalue())

    def test_notification_test_does_not_contact_or_stop_application(self):
        with patch('sys.argv', ['probe', '--simulate-failure']), patch.object(probe, 'check') as check, redirect_stdout(io.StringIO()):
            self.assertEqual(probe.main(), 1)
        check.assert_not_called()

    def test_synthetic_request_lists_tools_but_never_executes_one(self):
        calls = []
        def transport(url, method='GET', body=None):
            calls.append((url, method, body)); return healthy(url, method, body)
        probe.check(transport)
        self.assertEqual(json.loads(calls[-1][2])['method'], 'tools/list')
        self.assertNotIn('tools/call', str(calls))

    def test_redirects_are_not_followed(self):
        self.assertIsNone(probe.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example'))


if __name__ == '__main__': unittest.main()
