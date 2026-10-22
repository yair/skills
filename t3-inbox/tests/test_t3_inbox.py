"""Run from the skill directory: python3 -B -m unittest discover -s tests -v."""
from concurrent.futures import ThreadPoolExecutor
import base64
import errno
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/t3-inbox'
loader = importlib.machinery.SourceFileLoader('inbox', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
inbox = importlib.util.module_from_spec(spec)
loader.exec_module(inbox)


def server_frame(payload, opcode=1, fin=True):
    if isinstance(payload, str):
        payload = payload.encode()
    size = len(payload)
    head = bytes([(128 if fin else 0) | opcode])
    if size < 126:
        return head + bytes([size]) + payload
    if size < 65536:
        return head + b'\x7e' + struct.pack('!H', size) + payload
    return head + b'\x7f' + struct.pack('!Q', size) + payload


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = dict(os.environ)
        for key in list(self.env):
            if key.startswith(('T3CODE_', 'XDG_')):
                del self.env[key]
        self.env.update(HOME=str(self.root), T3CODE_HOME=str(self.root / 't3'),
                        XDG_CONFIG_HOME=str(self.root / 'config'),
                        XDG_CACHE_HOME=str(self.root / 'cache'),
                        XDG_STATE_HOME=str(self.root / 'state'))
        path = self.root / 't3/userdata/statev2.sqlite'
        path.parent.mkdir(parents=True)
        self.db = sqlite3.connect(path)
        self.db.executescript('''
            CREATE TABLE orchestration_v2_projection_threads
                (thread_id TEXT, project_id TEXT, title TEXT, payload_json TEXT,
                 deleted_at TEXT, archived_at TEXT);
            CREATE TABLE orchestration_v2_projection_provider_threads
                (thread_id TEXT, driver TEXT, payload_json TEXT);
            CREATE TABLE scheduled_tasks
                (task_id TEXT, title TEXT, prompt TEXT, enabled INTEGER, schedule_json TEXT,
                 project_id TEXT, thread_id TEXT, workspace_strategy_json TEXT,
                 model_selection_json TEXT, runtime_mode TEXT, interaction_mode TEXT, webhook_token TEXT,
                 creation_source TEXT);
        ''')
        self.thread = 'thread:child:example'
        self.native = '01a1536d-6fed-7902-8f6c-ec547880b557'
        self.config = {'projectId': 'project', 'modelSelection': {'instanceId': 'codex', 'model': 'test'},
                       'runtimeMode': 'auto', 'interactionMode': 'default',
                       'worktreePath': '/work/tree', 'branch': 'feature'}
        self.db.execute('INSERT INTO orchestration_v2_projection_threads VALUES (?,?,?,?,NULL,NULL)',
                        (self.thread, 'project', 'Build inbox', json.dumps(self.config)))
        self.mapping('codex', self.native)
        self.db.commit()
        self.patcher = patch.dict(os.environ, self.env, clear=True)
        self.patcher.start()

    def mapping(self, driver, native, ref_driver=None):
        value = {'nativeThreadRef': {'driver': ref_driver or driver, 'nativeId': native}}
        self.db.execute('INSERT INTO orchestration_v2_projection_provider_threads VALUES (?,?,?)',
                        (self.thread, driver, json.dumps(value)))

    def tearDown(self):
        self.patcher.stop()
        self.db.close()
        self.temp.cleanup()

    def run_hook(self, env=None, payload=None):
        result = subprocess.run(['python3', '-B', str(SCRIPT), 'hook'],
                                input=json.dumps(payload or {'session_id': self.native,
                                      'hook_event_name': 'UserPromptSubmit', 'prompt': 'test'}),
                                capture_output=True, text=True, env=env or self.env, timeout=7)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, '')
        return result.stdout

    def with_bearer(self):
        inbox.private_write(inbox.xdg('CONFIG') / 'bearer', 'test-bearer\n')

    def add_task(self, **changes):
        task = {'id': inbox.task_id(self.thread), 'title': 'Inbox', 'prompt': inbox.PROMPT,
                'enabled': True, 'schedule': {'type': 'webhook', 'filters': [inbox.TEXT_FILTER]},
                **inbox.thread_config(self.thread), 'creationSource': 'mcp',
                'webhook': {'path': '/api/hooks/test/secret'}}
        task.update(changes)
        self.db.execute('INSERT INTO scheduled_tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (task['id'], task['title'], task['prompt'], task['enabled'],
                         json.dumps(task['schedule']), task['projectId'], task['threadId'],
                         json.dumps(task['workspaceStrategy']), json.dumps(task['modelSelection']),
                         task['runtimeMode'], task['interactionMode'], 'secret',
                         task['creationSource']))
        self.db.commit()
        return task


class Fixture(Base):
    def test_exact_lookup_both_drivers(self):
        self.assertEqual(inbox.thread_of(self.native), self.thread)
        self.mapping('claudeAgent', 'claude-native')
        self.db.commit()
        self.assertEqual(inbox.thread_of('claude-native'), self.thread)
        with self.assertRaises(inbox.InboxError):
            inbox.thread_of(self.native[:-1])

    def test_lookup_excludes_wrong_driver_archived_deleted_and_ambiguous(self):
        self.mapping('codex', 'wrong', 'claudeAgent')
        self.db.commit()
        with self.assertRaises(inbox.InboxError):
            inbox.thread_of('wrong')
        for column in ('archived_at', 'deleted_at'):
            self.db.execute('UPDATE orchestration_v2_projection_threads SET '+column+'="now"')
            self.db.commit()
            with self.assertRaises(inbox.InboxError):
                inbox.thread_of(self.native)
            self.db.execute('UPDATE orchestration_v2_projection_threads SET '+column+'=NULL')
        self.db.execute('INSERT INTO orchestration_v2_projection_threads VALUES (?,?,?, ?,NULL,NULL)',
                        ('second', 'project', 'duplicate', json.dumps(self.config)))
        self.db.execute('INSERT INTO orchestration_v2_projection_provider_threads SELECT ?,driver,payload_json FROM orchestration_v2_projection_provider_threads WHERE thread_id=?', ('second', self.thread))
        self.db.commit()
        with self.assertRaises(inbox.InboxError):
            inbox.thread_of(self.native)

    def test_sqlite_connection_is_read_only(self):
        with inbox.database() as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute('DELETE FROM scheduled_tasks')

    def test_hook_no_t3_no_bearer_unknown_session(self):
        self.assertEqual(self.run_hook(), '')
        env = {**self.env, 'T3CODE_HOST': '127.0.0.1', 'T3CODE_PORT': '9'}
        self.assertEqual(self.run_hook(env), '')
        self.with_bearer()
        self.assertEqual(self.run_hook(env, {'session_id': 'unknown'}), '')
        log = (inbox.xdg('STATE') / 'hook.log').read_text()
        self.assertIn('not-in-t3', log)
        self.assertIn('no-bearer', log)
        self.assertIn('no-unique-session-mapping', log)
        self.assertNotIn('test-bearer', log)

    def test_hook_backend_failure_and_bad_json(self):
        self.with_bearer()
        with socket.socket() as server:
            server.bind(('127.0.0.1', 0))
            env = {**self.env, 'T3CODE_HOST': '127.0.0.1', 'T3CODE_PORT': str(server.getsockname()[1])}
            self.assertEqual(self.run_hook(env), '')
        result = subprocess.run(['python3', '-B', str(SCRIPT), 'hook'], input='{',
                                capture_output=True, text=True, env=env, timeout=7)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))

    def test_hook_timeout_including_lock_wait(self):
        self.with_bearer()
        os.environ.update(T3CODE_HOST='127.0.0.1', T3CODE_PORT='9')
        with inbox.thread_lock(self.thread):
            start = time.monotonic()
            self.assertEqual(self.run_hook(dict(os.environ)), '')
            self.assertLess(time.monotonic() - start, 5.5)

    def test_cached_hook_shape_and_one_line(self):
        self.with_bearer()
        self.add_task()
        env = {**self.env, 'T3CODE_HOST': '127.0.0.1', 'T3CODE_PORT': '9'}
        for extra in ({}, {'turn_id': 'codex-turn'}):
            output = json.loads(self.run_hook(env, {'session_id': self.native, **extra}))['hookSpecificOutput']
            self.assertEqual(output['hookEventName'], 'UserPromptSubmit')
            context = output['additionalContext']
            self.assertEqual(len(context.splitlines()), 1)
            self.assertTrue(context.startswith('Your T3 inbox is live: http://127.0.0.1:9/api/hooks/'))
            self.assertTrue(context.endswith("Don't auto-acknowledge inbox messages."))
        cache = inbox.xdg('CACHE') / (inbox.task_id(self.thread) + '.json')
        self.assertEqual(cache.stat().st_mode & 0o777, 0o600)
        self.assertEqual(cache.parent.stat().st_mode & 0o777, 0o700)

    def test_open_idempotence_and_model_runtime_interaction_drift(self):
        current = self.add_task()
        base = 'http://localhost:9'
        with patch.object(inbox, 'rpc') as rpc:
            first = inbox.open_inbox(self.thread, base, 'token')
            self.assertEqual(first, inbox.open_inbox(self.thread, base, 'token'))
            rpc.assert_not_called()
        for key, value in [('modelSelection', {'instanceId': 'other', 'model': 'new'}),
                           ('runtimeMode', 'full-access'), ('interactionMode', 'plan')]:
            updated = {**self.config, key: value}
            self.db.execute('UPDATE orchestration_v2_projection_threads SET payload_json=?', (json.dumps(updated),))
            self.db.commit()
            with patch.object(inbox, 'rpc', return_value={'task': current}) as rpc:
                inbox.open_inbox(self.thread, base, 'token')
                payload = rpc.call_args.args[3]
                self.assertEqual(payload[key], value)
                self.assertEqual(payload['id'], current['id'])

    def test_open_repairs_provider_creation_source(self):
        # agent/provider deliveries are provider continuations that Claude never sees.
        current = self.add_task(creationSource='provider')
        with patch.object(inbox, 'rpc', return_value={'task': current}) as rpc:
            inbox.open_inbox(self.thread, 'http://localhost:9', 'token')
            payload = rpc.call_args.args[3]
            self.assertEqual((payload['createdBy'], payload['creationSource']), ('agent', 'mcp'))

    def test_open_adds_the_text_filter_and_keeps_others(self):
        github = {'path': 'headers.x-github-event', 'op': 'exists'}
        current = self.add_task(schedule={'type': 'webhook', 'filters': [github]})
        saved = {**current, 'schedule': {'type': 'webhook', 'filters': [github, inbox.TEXT_FILTER]}}
        with patch.object(inbox, 'rpc', return_value={'task': saved}) as rpc:
            inbox.open_inbox(self.thread, 'http://localhost:9', 'token')
            self.assertEqual(rpc.call_args.args[3]['schedule'],
                             {'type': 'webhook', 'filters': [github, inbox.TEXT_FILTER]})
        self.assertFalse((inbox.xdg('STATE') / 'hook.log').exists())
        self.assertEqual(inbox.TEXT_FILTER, {'path': 'body.text', 'op': 'notEquals', 'value': ''})

    def test_open_on_a_backend_without_filters_still_returns_the_url(self):
        current = self.add_task(schedule={'type': 'webhook'})
        with patch.object(inbox, 'rpc', return_value={'task': current}) as rpc:
            result = inbox.open_inbox(self.thread, 'http://localhost:9', 'token')
            rpc.assert_called_once()
        self.assertEqual(result['url'], 'http://localhost:9/api/hooks/test/secret')
        self.assertIn('backend-without-filters', (inbox.xdg('STATE') / 'hook.log').read_text())

    def test_refuses_when_other_users_can_read_t3_data(self):
        self.add_task()
        self.with_bearer()
        for mode, shared, refused in ((0o711, False, True), (0o750, True, True),
                                      (0o750, False, False), (0o700, True, False)):
            with self.subTest(mode=oct(mode), shared=shared):
                self.root.chmod(mode)
                with patch.object(inbox, 'shared_group', return_value=shared), \
                        patch.object(inbox, 'rpc') as rpc:
                    if refused:
                        with self.assertRaisesRegex(inbox.InboxError, '^t3-data-readable-by-others$'):
                            inbox.open_inbox(self.thread, 'http://localhost:9', 'token')
                        with self.assertRaisesRegex(inbox.InboxError, '^t3-data-readable-by-others$'):
                            inbox.login(True, 'http://localhost:9')
                    else:
                        inbox.open_inbox(self.thread, 'http://localhost:9', 'token')
                    rpc.assert_not_called()
        # A private database doesn't help when transcripts sit behind searchable directories.
        sessions = self.root / '.codex/sessions/2026'
        sessions.mkdir(parents=True)
        (sessions / 'rollout.jsonl').write_text('{}')
        for directory in (self.root / '.codex', self.root / '.codex/sessions', sessions):
            directory.chmod(0o711)
        (self.root / 't3').chmod(0o700)
        self.root.chmod(0o711)
        with patch.object(inbox, 'shared_group', return_value=False):
            with self.assertRaisesRegex(inbox.InboxError, '^t3-data-readable-by-others$'):
                inbox.login(True, 'http://localhost:9')
            (self.root / '.codex').chmod(0o700)
            inbox.require_private()
        (self.root / 't3').chmod(0o755)
        env = {**self.env, 'T3CODE_HOST': '127.0.0.1', 'T3CODE_PORT': '9'}
        self.assertEqual(self.run_hook(env), '')
        self.assertIn('t3-data-readable-by-others', (inbox.xdg('STATE') / 'hook.log').read_text())
        self.root.chmod(0o700)

    def test_concurrent_open_creates_once(self):
        config = inbox.thread_config(self.thread)
        saved = []
        barrier = threading.Barrier(2)
        def save(base, token, method, payload):
            time.sleep(0.05)
            saved.append({**payload, 'webhook': {'path': '/api/hooks/test/secret'}})
            return {'task': saved[0]}
        def open_one():
            barrier.wait()
            return inbox.open_inbox(self.thread, 'http://localhost', 'token')
        with patch.object(inbox, 'thread_config', return_value=config), \
             patch.object(inbox, 'read_task', side_effect=lambda _: saved[0] if saved else None), \
             patch.object(inbox, 'rpc', side_effect=save) as rpc, ThreadPoolExecutor(2) as pool:
            first, second = list(pool.map(lambda _: open_one(), range(2)))
            self.assertEqual(first, second)
            self.assertEqual(rpc.call_count, 1)

    def test_gc_identity_and_archival(self):
        task = self.add_task()
        self.assertTrue(inbox.is_inbox(task))
        self.assertFalse(inbox.is_inbox({**task, 'id': str(uuid.uuid4())}))
        self.assertFalse(inbox.is_inbox({**task, 'title': 'Other'}))
        self.assertFalse(inbox.stale(self.thread))
        self.db.execute('UPDATE orchestration_v2_projection_threads SET archived_at="now"')
        self.db.commit()
        self.assertTrue(inbox.stale(self.thread))
        self.assertTrue(inbox.stale('missing'))
        result = subprocess.run(['python3', '-B', str(SCRIPT), 'gc', '--dry-run'],
                                capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), 'would-delete '+task['id'])
        self.assertIsNotNone(inbox.read_task(task['id']))

    def test_systemctl_fallback_and_explicit_override(self):
        output = subprocess.CompletedProcess([], 0, 'T3CODE_HOST=100.64.0.2 T3CODE_PORT=3773 OTHER="has spaces"')
        with patch.object(inbox.subprocess, 'run', return_value=output) as run:
            self.assertEqual(inbox.base_url(), 'http://100.64.0.2:3773')
            self.assertEqual(inbox.base_url('https://example.com/'), 'https://example.com')
            self.assertEqual(run.call_count, 1)


    def runtime(self, version='9.9.9', state=None):
        runtime = self.root / 't3/runtime'
        binary = runtime / 'versions' / version / 't3'
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$(dirname "$0")/argv"\n'
                          'echo \'{"token": "issued-token", "id": "s1", "label": "t3-inbox"}\'\n')
        binary.chmod(0o755)
        (runtime / 'service-state.json').write_text(json.dumps(state or {'protocol': 3, 'activeVersion': version}))
        return binary

    def test_login_runs_the_backends_own_t3(self):
        binary = self.runtime()
        npx = self.root / 'bin/npx'
        npx.parent.mkdir()
        npx.write_text('#!/bin/sh\ntouch "$0.ran"\nexit 1\n')
        npx.chmod(0o755)
        with patch.dict(os.environ, {'PATH': f"{npx.parent}:{os.environ['PATH']}"}), \
                patch('sys.stdout', new_callable=io.StringIO) as out:
            inbox.login(False, None)
        argv = (binary.parent / 'argv').read_text().split()
        self.assertEqual(argv[:3], ['auth', 'session', 'issue'])
        self.assertIn('orchestration:operate', argv)
        self.assertFalse(Path(str(npx) + '.ran').exists())
        self.assertEqual((inbox.xdg('CONFIG') / 'bearer').read_text(), 'issued-token\n')
        self.assertNotIn('issued-token', out.getvalue())

    def test_login_refuses_a_missing_or_odd_runtime(self):
        for state in (None, {'activeVersion': '../../bin'}, {'activeVersion': ''}, {'protocol': 3}):
            with self.subTest(state=state):
                runtime = self.root / 't3/runtime'
                if state is None:
                    (runtime / 'service-state.json').unlink(missing_ok=True)
                else:
                    runtime.mkdir(parents=True, exist_ok=True)
                    (runtime / 'service-state.json').write_text(json.dumps(state))
                with self.assertRaisesRegex(inbox.InboxError, '^t3-runtime-unavailable$'):
                    inbox.login(False, None)
        self.runtime(version='1.0.0', state={'activeVersion': '2.0.0'})
        with self.assertRaisesRegex(inbox.InboxError, '^t3-runtime-unavailable$'):
            inbox.login(False, None)


class Launchers(Base):
    NAME = 'Engine launch: zhizi-admin'
    HOOK = '/api/hooks/launch/launcher-secret'

    def setUp(self):
        super().setUp()
        self.with_bearer()
        self.prompt = self.root / 'prompt'
        self.prompt.write_text('Launch request:\n{{body.text}}\n')
        self.out = self.root / 'out' / 'url'
        self.out.parent.mkdir()

    def add_launcher(self, name=NAME, project='project', **changes):
        values = {'task_id': inbox.launcher_id(project, name), 'title': name, 'prompt': 'p',
                  'enabled': 1, 'schedule_json': json.dumps({'type': 'webhook', 'filters': [inbox.TEXT_FILTER]}),
                  'project_id': project, 'thread_id': None, 'workspace_strategy_json': '{"type": "root"}',
                  'model_selection_json': json.dumps(self.config['modelSelection']),
                  'runtime_mode': 'auto', 'interaction_mode': 'default',
                  'webhook_token': 'launcher-secret', 'creation_source': 'mcp', **changes}
        self.db.execute('INSERT INTO scheduled_tasks (%s) VALUES (%s)' % (
            ','.join(values), ','.join('?' * len(values))), list(values.values()))
        self.db.commit()
        return inbox.read_task(values['task_id'])

    def saved(self, base, token, method, payload):
        return {'task': {**payload, 'webhook': {'path': self.HOOK}}}

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(inbox.sys, 'argv', ['t3-inbox', *argv]), \
                patch.object(inbox.sys, 'stdout', out), patch.object(inbox.sys, 'stderr', err):
            code = inbox.main()
        return code, out.getvalue(), err.getvalue()

    def test_identity_is_per_project_and_name(self):
        identifier = inbox.launcher_id('project', self.NAME)
        self.assertEqual(identifier, str(uuid.uuid5(uuid.UUID('7b1def85-152e-512f-a5d6-68a161433cd5'),
                                                    'launcher:project:' + self.NAME)))
        self.assertNotEqual(identifier, inbox.launcher_id('other', self.NAME))
        self.assertNotEqual(identifier, inbox.launcher_id('project', 'Other'))
        launcher = self.add_launcher()
        self.assertTrue(inbox.is_launcher(launcher))
        for bad in ({'threadId': self.thread}, {'title': 'Renamed'}, {'projectId': 'other'},
                    {'workspaceStrategy': {'type': 'existing_worktree', 'worktreePath': '/w'}},
                    {'schedule': {'type': 'interval', 'everyMs': 1000}}):
            with self.subTest(bad=bad):
                self.assertFalse(inbox.is_launcher({**launcher, **bad}))

    def test_names(self):
        for name in (self.NAME, 'x', 'n' * 100, 'Ünïcode name'):
            self.assertEqual(inbox.launcher_name(name), name)
        for name in ('', ' lead', 'trail ', 'two\nlines', 'tab\there', 'n' * 101):
            with self.subTest(name=name), self.assertRaisesRegex(inbox.InboxError, '^invalid-launcher-name$'):
                inbox.launcher_name(name)

    def test_session_thread(self):
        self.assertEqual(inbox.session_thread('explicit'), 'explicit')
        with self.assertRaisesRegex(inbox.InboxError, '^no-session-thread-use-thread$'):
            inbox.session_thread()
        os.environ['CODEX_THREAD_ID'] = self.native
        self.assertEqual(inbox.session_thread(), self.thread)
        # An outer session that isn't a T3 thread doesn't count.
        os.environ['CLAUDE_CODE_SESSION_ID'] = 'not-a-t3-session'
        self.assertEqual(inbox.session_thread(), self.thread)
        self.db.execute('INSERT INTO orchestration_v2_projection_threads VALUES (?,?,?,?,NULL,NULL)',
                        ('other-thread', 'project', 'Other', json.dumps(self.config)))
        self.db.execute('INSERT INTO orchestration_v2_projection_provider_threads VALUES (?,?,?)',
                        ('other-thread', 'claudeAgent', json.dumps(
                            {'nativeThreadRef': {'driver': 'claudeAgent', 'nativeId': 'claude-native'}})))
        self.db.commit()
        os.environ['CLAUDE_CODE_SESSION_ID'] = 'claude-native'
        with self.assertRaisesRegex(inbox.InboxError, '^ambiguous-session-thread-use-thread$'):
            inbox.session_thread()

    def test_open_saves_a_root_launcher_from_the_threads_settings(self):
        with patch.object(inbox, 'rpc', side_effect=self.saved) as rpc:
            result, url = inbox.open_launcher(self.NAME, 'tmpl {{body.text}}', self.thread,
                                              'http://localhost:9', 'token')
        method, payload = rpc.call_args.args[2:]
        self.assertEqual(method, 'scheduledTasks.upsert')
        # The thread sits in a worktree on a branch; the launcher ignores both.
        self.assertEqual(payload, {
            'id': inbox.launcher_id('project', self.NAME), 'title': self.NAME,
            'prompt': 'tmpl {{body.text}}', 'enabled': True,
            'schedule': {'type': 'webhook', 'filters': [inbox.TEXT_FILTER]},
            'projectId': 'project', 'threadId': None, 'workspaceStrategy': {'type': 'root'},
            'modelSelection': self.config['modelSelection'], 'runtimeMode': 'auto',
            'interactionMode': 'default', 'createdBy': 'agent', 'creationSource': 'mcp'})
        self.assertEqual(result, {'taskId': payload['id'], 'projectId': 'project', 'title': self.NAME,
                                  'workspace': {'type': 'root'}})
        self.assertEqual(url, 'http://localhost:9' + self.HOOK)

    def test_reopen_updates_in_place_and_keeps_hand_added_filters(self):
        github = {'path': 'headers.x-github-event', 'op': 'exists'}
        current = self.add_launcher(enabled=0, schedule_json=json.dumps(
            {'type': 'webhook', 'filters': [github, inbox.TEXT_FILTER]}))
        with patch.object(inbox, 'rpc', side_effect=self.saved) as rpc:
            result, _ = inbox.open_launcher(self.NAME, 'new', self.thread, 'http://localhost:9', 'token')
        payload = rpc.call_args.args[3]
        self.assertEqual((payload['id'], result['taskId']), (current['id'], current['id']))
        self.assertEqual(payload['schedule']['filters'], [github, inbox.TEXT_FILTER])
        self.assertEqual((payload['prompt'], payload['enabled']), ('new', True))

    def test_open_refuses_a_task_that_is_not_a_launcher(self):
        self.add_launcher(thread_id=self.thread)
        with patch.object(inbox, 'rpc') as rpc, \
                self.assertRaisesRegex(inbox.InboxError, '^task-identity-collision$'):
            inbox.open_launcher(self.NAME, 'p', self.thread, 'http://localhost:9', 'token')
        rpc.assert_not_called()

    def test_open_parks_the_launcher_on_a_backend_without_filters(self):
        def old_backend(base, token, method, payload):
            return {'task': {**payload, 'schedule': {'type': 'webhook'}, 'webhook': {'path': self.HOOK}}}
        with patch.object(inbox, 'rpc', side_effect=old_backend) as rpc, \
                self.assertRaisesRegex(inbox.InboxError, '^backend-without-filters$'):
            inbox.open_launcher(self.NAME, 'p', self.thread, 'http://localhost:9', 'token')
        self.assertEqual(rpc.call_count, 2)
        self.assertFalse(rpc.call_args.args[3]['enabled'])

    def test_cli_open_writes_the_url_only_to_the_file(self):
        self.out.parent.chmod(0o755)
        os.environ['CLAUDE_CODE_SESSION_ID'] = self.native
        with patch.object(inbox, 'rpc', side_effect=self.saved) as rpc:
            code, out, err = self.cli('launcher', 'open', self.NAME, '--prompt-file', str(self.prompt),
                                      '--url-file', str(self.out), '--base', 'http://localhost:9')
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(rpc.call_args.args[3]['prompt'], self.prompt.read_text())
        self.assertEqual(json.loads(out), {'taskId': inbox.launcher_id('project', self.NAME),
                                           'projectId': 'project', 'title': self.NAME,
                                           'workspace': {'type': 'root'}})
        self.assertNotIn('launcher-secret', out)
        self.assertEqual(self.out.read_text(), 'http://localhost:9' + self.HOOK + '\n')
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.out.parent.stat().st_mode & 0o777, 0o755)
        self.assertEqual(os.listdir(self.out.parent), ['url'])
        self.assertFalse((inbox.xdg('STATE') / 'hook.log').exists())

    def test_cli_open_failures_are_reason_codes(self):
        bad = self.root / 'bad'
        cases = [(['--prompt-file', str(self.root / 'missing')], 'invalid-prompt-file'),
                 (['--prompt-file', str(self.prompt), '--thread', 'missing'], 'thread-unavailable'),
                 (['--prompt-file', str(self.prompt)], 'no-session-thread-use-thread'),
                 (['--prompt-file', str(bad), '--thread', self.thread], 'invalid-prompt-file')]
        bad.write_bytes(b'\xff\xfe')
        for extra, code in cases:
            with self.subTest(code=code), patch.object(inbox, 'rpc', side_effect=self.saved):
                result = self.cli('launcher', 'open', self.NAME, '--url-file', str(self.out),
                                  '--base', 'http://localhost:9', *extra)
                self.assertEqual(result, (1, '', 't3-inbox: ' + code + '\n'))
                self.assertFalse(self.out.exists())
        with patch.object(inbox, 'rpc', side_effect=self.saved):
            result = self.cli('launcher', 'open', self.NAME, '--prompt-file', str(self.prompt),
                              '--url-file', str(self.root / 'absent/url'), '--thread', self.thread,
                              '--base', 'http://localhost:9')
        self.assertEqual(result, (1, '', 't3-inbox: url-file-unwritable\n'))

    def test_sandbox_denials_get_a_reason_code(self):
        argv = ['launcher', 'open', self.NAME, '--prompt-file', str(self.prompt), '--url-file', str(self.out),
                '--thread', self.thread, '--base', 'http://localhost:9']
        for error, code in ((PermissionError(errno.EPERM, 'x'), 'denied-run-outside-sandbox'),
                            (OSError(errno.EROFS, 'x'), 'denied-run-outside-sandbox'),
                            (ConnectionRefusedError(errno.ECONNREFUSED, 'x'), 'ConnectionRefusedError')):
            with self.subTest(code=code), patch.object(inbox, 'rpc', side_effect=error):
                self.assertEqual(self.cli(*argv), (1, '', 't3-inbox: ' + code + '\n'))

    def test_list_and_rm(self):
        launcher = self.add_launcher()
        self.add_launcher(name='Other', project='elsewhere')
        self.add_task()
        code, out, err = self.cli('launcher', 'list')
        self.assertEqual((code, err), (0, ''))
        lines = [json.loads(line) for line in out.splitlines()]
        self.assertEqual(sorted(line['title'] for line in lines), [self.NAME, 'Other'])
        self.assertEqual(set(lines[0]), {'taskId', 'projectId', 'title', 'enabled'})
        self.assertNotIn('secret', out)
        with patch.object(inbox, 'rpc') as rpc:
            self.assertEqual(self.cli('launcher', 'rm', 'Missing', '--project', 'project', '--base', 'http://x')[2],
                             't3-inbox: launcher-unavailable\n')
            rpc.assert_not_called()
            code, out, _ = self.cli('launcher', 'rm', self.NAME, '--thread', self.thread, '--base', 'http://x')
            self.assertEqual(code, 0)
            self.assertEqual(rpc.call_args.args[2:], ('scheduledTasks.delete', {'id': launcher['id']}))
            self.assertEqual(json.loads(out)['taskId'], launcher['id'])

    def test_gc_and_url_leave_launchers_alone(self):
        # Even one titled like an inbox: is_inbox needs a thread, which a launcher lacks.
        for name in (self.NAME, 'Inbox'):
            launcher = self.add_launcher(name=name)
            self.assertFalse(inbox.is_inbox(launcher))
            self.assertEqual(self.cli('url', launcher['id'], '--base', 'http://x'),
                             (1, '', 't3-inbox: inbox-unavailable\n'))
        self.assertEqual(inbox.inboxes(), [])
        with patch.object(inbox, 'rpc') as rpc:
            self.assertEqual(self.cli('gc', '--base', 'http://x'), (0, '', ''))
            rpc.assert_not_called()
        self.assertEqual(len(inbox.launchers()), 2)


class Protocol(unittest.TestCase):
    def test_template_envelope_and_stable_identity(self):
        self.assertEqual(inbox.PROMPT, 'Inbox message from {{body.from}}: {{body.subject}}\n{{body.text}}\n{{body.url}}\nReply to: {{body.reply_to}}')
        self.assertEqual(inbox.ENVELOPE_FIELDS, ('from', 'subject', 'text', 'url', 'reply_to'))
        self.assertEqual(inbox.task_id('thread:child:example'), str(uuid.uuid5(uuid.UUID('7b1def85-152e-512f-a5d6-68a161433cd5'), 'thread:child:example')))
        self.assertNotEqual(inbox.task_id('a'), inbox.task_id('b'))

    def test_client_masking_and_lengths(self):
        for size in (0, 5, 125, 126, 65535, 65536):
            data = b'x' * size
            frame = inbox.encode_frame(data)
            self.assertEqual(frame[0], 129)
            self.assertTrue(frame[1] & 128)
            length = frame[1] & 127
            offset = 2
            if length == 126:
                length = struct.unpack('!H', frame[2:4])[0]
                offset = 4
            elif length == 127:
                length = struct.unpack('!Q', frame[2:10])[0]
                offset = 10
            self.assertEqual(length, size)
            mask = frame[offset:offset+4]
            self.assertEqual(bytes(b ^ mask[i % 4] for i, b in enumerate(frame[offset+4:])), data)

    def test_server_decoding_lengths(self):
        for size in (0, 125, 126, 65535, 65536):
            self.assertEqual(inbox.decode_frame(io.BytesIO(server_frame(b'x'*size)).read), (True, 1, b'x'*size))

    def test_fragmented_utf8_with_interleaved_ping(self):
        data = 'hello — inbox'.encode()
        stream = io.BytesIO(server_frame(data[:7], fin=False) + server_frame(b'ping', opcode=9)
                            + server_frame(b'', opcode=10) + server_frame(data[7:], opcode=0))
        ws = inbox.WebSocket('http://localhost', 'token')
        ws.read = stream.read
        with patch.object(ws, 'send') as send:
            self.assertEqual(ws.receive(), 'hello — inbox')
            send.assert_called_once_with(b'ping', 10)

    def test_upgrade_and_rpc_on_real_socket(self):
        errors = []
        with socket.socket() as server:
            server.bind(('127.0.0.1', 0))
            server.listen()
            server.settimeout(2)
            def serve():
                try:
                    with server.accept()[0] as connection:
                        connection.settimeout(2)
                        request = bytearray()
                        while not request.endswith(b'\r\n\r\n'):
                            request.extend(connection.recv(1))
                        self.assertIn(b'Authorization: Bearer test-token', request)
                        key = next(line.split(b':', 1)[1].strip() for line in request.split(b'\r\n')
                                   if line.lower().startswith(b'sec-websocket-key:'))
                        accept = base64.b64encode(hashlib.sha1(key + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())
                        connection.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: WebSocket\r\n'
                                           b'Connection: keep-alive, Upgrade\r\nSec-WebSocket-Accept: '+accept+b'\r\n\r\n')
                        self.assertTrue(connection.recv(4096)[1] & 128)
                        response = json.dumps([{'_tag': 'Ping'}, {'_tag': 'Exit', 'requestId': '1',
                                               'exit': {'_tag': 'Success', 'value': {'tasks': []}}}]).encode()
                        connection.sendall(server_frame(response[:10], fin=False) +
                                           server_frame(b'alive', opcode=9) + server_frame(response[10:], opcode=0))
                        connection.recv(4096)
                except Exception as exc:
                    errors.append(exc)
            worker = threading.Thread(target=serve)
            worker.start()
            try:
                result = inbox.rpc('http://127.0.0.1:'+str(server.getsockname()[1]),
                                   'test-token', 'scheduledTasks.list', {})
                self.assertEqual(result, {'tasks': []})
            finally:
                worker.join(3)
            self.assertFalse(worker.is_alive())
            if errors:
                raise errors[0]

    def test_invalid_frames_and_fragments(self):
        for frame in (b'\xc1\0', b'\x81\x80', b'\x09\0', b'\x89\x7e\0\x7e'):
            with self.assertRaises(inbox.InboxError):
                inbox.decode_frame(io.BytesIO(frame).read)
        for frame in (server_frame(b'x', opcode=0), server_frame(b'x', opcode=2),
                      server_frame(b'x', fin=False) + server_frame(b'y')):
            ws = inbox.WebSocket('http://localhost', 'token')
            ws.read = io.BytesIO(frame).read
            with self.assertRaises(inbox.InboxError):
                ws.receive()


if __name__ == '__main__':
    unittest.main()
