"""helpers/cmd-watch against a fake inbox and a check that reads a file. Run from the skill directory:
python3 -B -m unittest discover -s tests -v."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_gh_watch import Fake, INBOX_SECRET, THREAD

HELPER = Path(__file__).resolve().parents[1] / 'helpers/cmd-watch'
NAME = 'php-image'


class CmdWatch(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inbox = Fake()
        self.addCleanup(self.inbox.close)
        self.addCleanup(self.temp.cleanup)
        self.inbox.routes[f'/api/hooks/task/{INBOX_SECRET}'] = (202, {'accepted': True}, {})
        self.stub = self.root / 'inbox-stub'
        self.stub.write_text('import sys\nassert sys.argv[1:3] == ["url", "%s"], sys.argv\n'
                             'print("%s/api/hooks/task/%s")\n' % (THREAD, self.inbox.origin, INBOX_SECRET))
        self.value = self.root / 'value'
        self.value.write_text('PHP 8.3.29 (cli)\n')
        self.marker = self.root / 'ran'
        self.check = f'touch {self.marker}; cat {self.value}'
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('XDG_')}
        self.env.update(HOME=str(self.root), XDG_STATE_HOME=str(self.root / 'state'))
        self.state = self.root / 'state/t3-inbox/cmd-watch' / THREAD / NAME

    def run_watch(self, *extra, check=None):
        argv = [sys.executable, str(HELPER), '--thread', THREAD, '--name', NAME,
                '--check', check or self.check, '--inbox-cmd', f'{sys.executable} {self.stub}', *extra]
        result = subprocess.run(argv, env=self.env, capture_output=True, text=True, timeout=60)
        output = result.stdout + result.stderr
        self.assertNotIn(INBOX_SECRET, output)
        return result.returncode, output

    def seed(self):
        code, out = self.run_watch()
        self.assertEqual(code, 0, out)
        self.assertIn('seeded', out)

    def test_first_run_seeds_without_sending(self):
        self.seed()
        self.assertEqual(self.inbox.posts(), [])
        self.assertEqual(self.state.joinpath('last').read_text(), 'PHP 8.3.29 (cli)')
        self.assertEqual(oct(self.state.stat().st_mode & 0o777), '0o700')

    def test_change_one_post_then_nothing(self):
        self.seed()
        code, out = self.run_watch()
        self.assertEqual(code, 0, out)
        self.assertIn('no change', out)
        self.value.write_text('PHP 8.3.36 (cli)\n')
        code, out = self.run_watch('--note', 'Next: task ca63bde7')
        self.assertEqual(code, 0, out)
        self.assertNotIn('8.3.36', out)   # the log never carries check output
        posts = self.inbox.posts()
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]['subject'], f'{NAME} changed')
        self.assertEqual(posts[0]['text'],
                         'Was:\nPHP 8.3.29 (cli)\n\nNow:\nPHP 8.3.36 (cli)\n\nNext: task ca63bde7')
        self.assertEqual(set(posts[0]), {'from', 'subject', 'text'})
        code, out = self.run_watch()
        self.assertIn('no change', out)
        self.assertEqual(len(self.inbox.posts()), 1)

    def test_failing_check_sends_and_records_nothing(self):
        self.seed()
        code, out = self.run_watch(check='echo surprise; exit 3')
        self.assertEqual(code, 1)
        self.assertIn('check exited 3', out)
        self.assertNotIn('surprise', out)
        self.assertEqual(self.inbox.posts(), [])
        self.assertEqual(self.state.joinpath('last').read_text(), 'PHP 8.3.29 (cli)')

    def test_check_timeout(self):
        self.seed()
        code, out = self.run_watch('--timeout', '1', check='sleep 5')
        self.assertEqual(code, 1)
        self.assertIn('check timed out after 1s', out)
        self.assertEqual(self.inbox.posts(), [])

    def test_failed_delivery_stays_pending(self):
        self.seed()
        self.value.write_text('PHP 8.3.36 (cli)\n')
        self.inbox.routes[f'/api/hooks/task/{INBOX_SECRET}'] = (500, {}, {})
        code, out = self.run_watch()
        self.assertEqual(code, 1)
        self.assertIn('inbox answered HTTP 500', out)
        self.assertIn('stays pending', out)
        self.assertEqual(self.state.joinpath('last').read_text(), 'PHP 8.3.29 (cli)')
        self.inbox.routes[f'/api/hooks/task/{INBOX_SECRET}'] = (202, {}, {})
        code, out = self.run_watch()
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.inbox.posts()), 2)   # the failed attempt and the redelivery
        self.assertEqual(self.state.joinpath('last').read_text(), 'PHP 8.3.36 (cli)')

    def test_inbox_lookup_failure_hides_urls(self):
        self.seed()
        self.value.write_text('PHP 8.3.36 (cli)\n')
        self.stub.write_text('import sys\nsys.stderr.write("cannot reach http://h/api/hooks/t/%s\\n")\nsys.exit(1)\n'
                             % INBOX_SECRET)
        code, out = self.run_watch()   # run_watch asserts the secret is not printed
        self.assertEqual(code, 1)
        self.assertIn('inbox lookup failed: cannot reach <url>', out)

    def test_held_lock_skips_without_running_the_check(self):
        self.seed()
        self.marker.unlink()
        with open(self.state / 'lock', 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            code, out = self.run_watch()
        self.assertEqual(code, 0, out)
        self.assertIn('another cmd-watch run holds this state', out)
        self.assertFalse(self.marker.exists())

    def test_dry_run_sends_and_records_nothing(self):
        code, out = self.run_watch('--dry-run')
        self.assertIn('dry run, nothing written', out)
        self.assertFalse(self.state.joinpath('last').exists())
        self.seed()
        self.value.write_text('PHP 8.3.36 (cli)\n')
        code, out = self.run_watch('--dry-run')
        self.assertEqual(code, 0, out)
        self.assertIn('"subject": "php-image changed"', out)
        self.assertEqual(self.inbox.posts(), [])
        self.assertEqual(self.state.joinpath('last').read_text(), 'PHP 8.3.29 (cli)')

    def test_name_must_be_a_plain_label(self):
        argv = [sys.executable, str(HELPER), '--thread', THREAD, '--name', '../x', '--check', 'true']
        result = subprocess.run(argv, env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 1)
        self.assertIn('--name wants', result.stdout)
        self.assertFalse((self.root / 'state').exists())


if __name__ == '__main__':
    unittest.main()
