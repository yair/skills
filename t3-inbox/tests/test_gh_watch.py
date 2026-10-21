"""helpers/gh-watch against a loopback fake GitHub and a fake inbox. Run from the skill directory:
python3 -B -m unittest discover -s tests -v."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

HELPER = Path(__file__).resolve().parents[1] / 'helpers/gh-watch'
GH_SECRET = 'ghp_TESTSECRETdonotprint'
INBOX_SECRET = 'INBOXTOKENdonotprint'
THREAD = 'thread-1'


class Fake:
    """A loopback HTTP server: routes map a path (with query) to (status, JSON body, headers)."""

    def __init__(self):
        self.routes, self.requests = {}, []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def answer(self, body=None):
                fake.requests.append({'method': self.command, 'path': self.path, 'body': body,
                                      'auth': self.headers.get('Authorization')})
                status, payload, headers = fake.routes.get(self.path.split('?')[0], (404, {}, {}))
                if callable(payload):
                    payload = payload(self.path)
                data = json.dumps(payload).encode()
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self.answer()

            def do_POST(self):
                self.answer(json.loads(self.rfile.read(int(self.headers['Content-Length']))))

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.origin = 'http://127.0.0.1:%d' % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def posts(self):
        return [r['body'] for r in self.requests if r['method'] == 'POST']


def notification(nid, repo, number, updated, reason='comment', kind='issues', comment=None, title=None):
    return {'id': str(nid), 'reason': reason, 'updated_at': updated,
            'repository': {'full_name': repo},
            'subject': {'type': 'PullRequest' if kind == 'pulls' else 'Issue',
                        'title': title or f'{repo} #{number}',
                        'url': f'https://api.github.com/repos/{repo}/{kind}/{number}',
                        'latest_comment_url': comment}}


class GhWatch(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.github, self.inbox = Fake(), Fake()
        self.addCleanup(self.github.close)
        self.addCleanup(self.inbox.close)
        self.addCleanup(self.temp.cleanup)
        self.inbox.routes[f'/api/hooks/task/{INBOX_SECRET}'] = (202, {'accepted': True}, {})
        self.stub = self.root / 'inbox-stub'
        self.stub.write_text('import sys\nassert sys.argv[1:3] == ["url", "%s"], sys.argv\n'
                             'print("%s/api/hooks/task/%s")\n' % (THREAD, self.inbox.origin, INBOX_SECRET))
        self.notes = []
        self.github.routes['/notifications'] = (200, lambda path: self.notes, {})
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('GH_', 'GITHUB_', 'XDG_'))}
        self.env.update(HOME=str(self.root), XDG_STATE_HOME=str(self.root / 'state'), GH_TOKEN=GH_SECRET)
        self.state = self.root / 'state/t3-inbox/gh-watch' / THREAD

    def run_watch(self, *extra, watch=('--repo', '^acme/app$')):
        argv = [sys.executable, str(HELPER), '--thread', THREAD, *watch, '--api', self.github.origin,
                '--inbox-cmd', f'{sys.executable} {self.stub}', *extra]
        result = subprocess.run(argv, env=self.env, capture_output=True, text=True, timeout=60)
        output = result.stdout + result.stderr
        self.assertNotIn(GH_SECRET, output)
        self.assertNotIn(INBOX_SECRET, output)
        return result.returncode, output

    def seed(self, *extra, **kwargs):
        code, out = self.run_watch(*extra, **kwargs)
        self.assertEqual(code, 0, out)
        self.assertIn('seeded', out)
        self.state.joinpath('since').write_text('2026-10-21T10:00:00Z\n')

    def test_first_run_seeds_without_sending(self):
        self.notes.append(notification(1, 'acme/app', 5, '2026-10-21T09:00:00Z'))
        code, out = self.run_watch()
        self.assertEqual(code, 0, out)
        self.assertIn('seeded', out)
        self.assertEqual(self.inbox.posts(), [])
        self.assertTrue(self.state.joinpath('since').exists())
        self.assertEqual(oct(self.state.stat().st_mode & 0o777), '0o700')

    def test_new_activity_one_post_then_nothing(self):
        self.seed()
        self.notes.append(notification(1, 'acme/app', 5, '2026-10-21T11:00:00Z', title='Crash on save'))
        code, out = self.run_watch('--note', 'Context: notes.md')
        self.assertEqual(code, 0, out)
        posts = self.inbox.posts()
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]['subject'], '1 GitHub update(s)')
        self.assertIn('acme/app#5 [comment] Crash on save — https://github.com/acme/app/issues/5', posts[0]['text'])
        self.assertTrue(posts[0]['text'].endswith('\n\nContext: notes.md'))
        self.assertEqual(posts[0]['url'], 'https://github.com/acme/app/issues/5')
        self.assertEqual(set(posts[0]), {'from', 'subject', 'text', 'url'})
        code, out = self.run_watch()
        self.assertEqual(code, 0, out)
        self.assertIn('no new activity', out)
        self.assertEqual(len(self.inbox.posts()), 1)
        # an update of the same thread is new again
        self.notes[0]['updated_at'] = '2026-10-21T12:00:00Z'
        self.run_watch()
        self.assertEqual(len(self.inbox.posts()), 2)

    def test_filters(self):
        self.seed(watch=('--repo', '^acme/app$', '--issue', 'other/lib#7'))
        self.notes.extend([
            notification(1, 'acme/app', 1, '2026-10-21T11:00:00Z', reason='ci_activity'),
            notification(2, 'acme/app-two', 2, '2026-10-21T11:01:00Z'),
            notification(3, 'other/lib', 8, '2026-10-21T11:02:00Z'),
            notification(4, 'other/lib', 7, '2026-10-21T11:03:00Z', kind='pulls'),
            notification(5, 'acme/app', 9, '2026-10-21T11:04:00Z', reason='mention')])
        code, out = self.run_watch(watch=('--repo', '^acme/app$', '--issue', 'other/lib#7'))
        self.assertEqual(code, 0, out)
        text = self.inbox.posts()[0]['text']
        self.assertIn('other/lib#7 [comment]', text)
        self.assertIn('https://github.com/other/lib/pull/7', text)
        self.assertIn('acme/app#9 [mention]', text)
        for dropped in ('acme/app#1', 'app-two', 'other/lib#8'):
            self.assertNotIn(dropped, text)
        self.assertLess(text.index('other/lib#7'), text.index('acme/app#9'))   # oldest first

    def test_releases(self):
        rels = [{'tag_name': 'v2', 'prerelease': False, 'draft': False, 'published_at': 'x', 'html_url': 'https://github.com/acme/app/releases/v2'},
                {'tag_name': 'v1', 'prerelease': False, 'draft': False, 'published_at': 'x', 'html_url': 'https://github.com/acme/app/releases/v1'}]
        self.github.routes['/repos/acme/app/releases'] = (200, lambda path: rels, {})
        self.seed(watch=('--release-repo', 'acme/app'))
        code, out = self.run_watch(watch=('--release-repo', 'acme/app'))
        self.assertIn('no new activity', out)   # seeded releases are not news
        rels.insert(0, {'tag_name': 'v3-beta', 'prerelease': True, 'draft': False})
        rels.insert(0, {'tag_name': 'v3', 'prerelease': False, 'draft': False, 'published_at': 'x', 'html_url': 'https://github.com/acme/app/releases/v3'})
        code, out = self.run_watch(watch=('--release-repo', 'acme/app'))
        self.assertEqual(code, 0, out)
        posts = self.inbox.posts()
        self.assertEqual(len(posts), 1)
        self.assertIn('acme/app released v3 — https://github.com/acme/app/releases/v3', posts[0]['text'])
        self.assertNotIn('v3-beta', posts[0]['text'])

    def test_failed_delivery_stays_pending(self):
        self.seed()
        self.notes.append(notification(1, 'acme/app', 5, '2026-10-21T11:00:00Z'))
        self.inbox.routes[f'/api/hooks/task/{INBOX_SECRET}'] = (500, {}, {})
        code, out = self.run_watch()
        self.assertEqual(code, 1)
        self.assertIn('inbox answered HTTP 500', out)
        self.assertIn('1 item(s) stay pending', out)
        self.assertEqual(self.state.joinpath('since').read_text().strip(), '2026-10-21T10:00:00Z')
        self.inbox.routes[f'/api/hooks/task/{INBOX_SECRET}'] = (202, {}, {})
        code, out = self.run_watch()
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.inbox.posts()), 2)   # the failed attempt and the redelivery

    def test_inbox_lookup_failure_hides_urls(self):
        self.seed()
        self.notes.append(notification(1, 'acme/app', 5, '2026-10-21T11:00:00Z'))
        self.stub.write_text('import sys\nsys.stderr.write("cannot reach http://h/api/hooks/t/%s\\n")\nsys.exit(1)\n'
                             % INBOX_SECRET)
        code, out = self.run_watch()   # run_watch asserts neither secret is printed
        self.assertEqual(code, 1)
        self.assertIn('inbox lookup failed: cannot reach <url>', out)

    def test_max_items_rest_next_run(self):
        self.seed()
        self.notes.extend(notification(i, 'acme/app', i, '2026-10-21T11:%02d:00Z' % i) for i in range(1, 26))
        code, out = self.run_watch()
        self.assertEqual(code, 0, out)
        first = self.inbox.posts()[0]
        self.assertEqual(first['subject'], '20 GitHub update(s) (25 pending, the rest next run)')
        self.assertNotIn('url', first)
        self.assertEqual(self.state.joinpath('since').read_text().strip(), '2026-10-21T10:00:00Z')
        code, out = self.run_watch()
        second = self.inbox.posts()[1]
        self.assertEqual(second['subject'], '5 GitHub update(s)')
        self.assertIn('acme/app#21 ', second['text'])
        self.assertIn('acme/app#25 ', second['text'])

    def test_pagination_and_token_scope(self):
        self.seed()
        self.notes.append(notification(1, 'acme/app', 5, '2026-10-21T11:00:00Z',
                                       comment=self.github.origin + '/repos/acme/app/issues/comments/9'))
        foreign = Fake()   # another origin (same host, other port) must never see a request
        self.addCleanup(foreign.close)
        foreign.routes['/steal'] = (200, {'user': {'login': 'mallory'}}, {})
        self.notes.append(notification(2, 'acme/app', 6, '2026-10-21T11:01:00Z',
                                       comment=foreign.origin + '/steal'))
        page2 = [notification(3, 'acme/app', 7, '2026-10-21T11:02:00Z')]
        first = self.notes[:]
        self.github.routes['/notifications'] = (200, lambda path: first, {'Link': f'<{self.github.origin}/page2>; rel="next"'})
        self.github.routes['/page2'] = (200, lambda path: page2, {})
        self.github.routes['/repos/acme/app/issues/comments/9'] = (200, {'user': {'login': 'alice'}}, {})
        code, out = self.run_watch()
        self.assertEqual(code, 0, out)
        text = self.inbox.posts()[0]['text']
        self.assertIn('acme/app#5 [comment, last comment by alice]', text)
        self.assertIn('acme/app#6 [comment] ', text)   # foreign comment URL: not fetched, no name
        self.assertIn('acme/app#7 ', text)
        gets = [r for r in self.github.requests if r['method'] == 'GET']
        self.assertTrue(all(r['auth'] == 'Bearer ' + GH_SECRET for r in gets))
        listing = [r['path'] for r in gets if r['path'].startswith('/notifications?')]
        self.assertEqual(len(listing), 1)
        self.assertIn('since=2026-10-21T09%3A50%3A00Z', listing[0])   # 10 min before the last poll
        self.assertIn('all=true', listing[0])
        self.assertEqual(foreign.requests, [])
        self.assertFalse(any(r['auth'] for r in self.inbox.requests))

    def test_github_error_is_reported(self):
        self.seed()
        self.github.routes['/notifications'] = (401, {'message': 'Bad credentials'}, {})
        code, out = self.run_watch()
        self.assertEqual(code, 1)
        self.assertIn('notifications: GitHub answered HTTP 401', out)

    def test_held_lock_skips(self):
        self.seed()
        self.notes.append(notification(1, 'acme/app', 5, '2026-10-21T11:00:00Z'))
        with open(self.state / 'lock', 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            code, out = self.run_watch()
        self.assertEqual(code, 0, out)
        self.assertIn('another gh-watch run holds this state', out)
        self.assertEqual(self.github.requests, [])   # a --repo seed asks GitHub nothing, and the skip asked nothing
        self.assertEqual(self.inbox.posts(), [])

    def test_dry_run_sends_and_records_nothing(self):
        self.seed()
        self.notes.append(notification(1, 'acme/app', 5, '2026-10-21T11:00:00Z'))
        before = {p.name: p.read_text() for p in self.state.iterdir() if p.name != 'lock'}
        code, out = self.run_watch('--dry-run')
        self.assertEqual(code, 0, out)
        self.assertIn('"subject": "1 GitHub update(s)"', out)
        self.assertIn('dry run: would deliver 1 of 1', out)
        self.assertEqual(self.inbox.posts(), [])
        self.assertEqual(before, {p.name: p.read_text() for p in self.state.iterdir() if p.name != 'lock'})

    def test_needs_something_to_watch(self):
        code, out = self.run_watch(watch=())
        self.assertEqual(code, 1)
        self.assertIn('nothing to watch', out)
        code, out = self.run_watch(watch=('--issue', 'not-an-issue'))
        self.assertEqual(code, 1)
        self.assertIn('--issue wants owner/repo#N', out)


if __name__ == '__main__':
    unittest.main()
