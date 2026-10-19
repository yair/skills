# Inbox spike report (2026-10-19)

Feasibility spike for zhizi-admin engine task b0c3178f, kept as the evidence
behind `scripts/t3-inbox`. The prototypes it names lived in `/tmp` and are gone.

One finding came later and overrides the report: tasks must be created with
`createdBy: "agent"`, `creationSource: "mcp"` (what MCP `schedule_task` uses).
T3's Claude adapter treats `agent`/`provider` deliveries as provider
continuation turns (`ClaudeAdapterV2.ts:2724`, `isClaudeProviderContinuationTurn`)
and never sends them to the model: the turn completes in milliseconds, silently.

---

Feasibility spike for Engine b0c3178f — 2026-10-19

**Q1: Yes, standalone scoped RPC works.** Tested on the existing research child
thread, without creating another thread or building T3. Both repositories stayed
unchanged. All SQLite access used `file:…?mode=ro`.

Prototype files:

- `/tmp/t3-inbox-spike/rpc.py`: minimal Effect RPC WebSocket client.
- `/tmp/t3-inbox-spike/spike.py`: issue session → create → list → curl POST →
  observe queued run → cancel test queue entry → delete task → revoke session.
- `/tmp/t3-inbox-spike/thread_of.py`: exact native-session-to-T3-thread lookup.
- `/tmp/t3-inbox-spike/evidence.json`: complete successful RPC frames and cleanup
  evidence, with credential tokens reduced to their first four characters.

Run the prototype against an explicitly chosen disposable research/test thread:

```bash
python3 -m venv --system-site-packages /tmp/t3-inbox-spike/venv
# This host already has websockets 16.0; otherwise install websockets in this venv.
/tmp/t3-inbox-spike/venv/bin/python /tmp/t3-inbox-spike/spike.py --thread THREAD_ID
```

The script issues precisely:

```bash
npx t3@latest auth session issue \
  --scope orchestration:read --scope orchestration:operate \
  --label t3-inbox-spike --ttl 1h --json
```

It stores the credential in a mode-600 file under `/tmp/t3-inbox-spike/`, revokes
the session in `finally`, and removes that file after successful revocation.

Connect to `ws://$T3CODE_HOST:$T3CODE_PORT/ws?orchestrationProtocol=2` with HTTP
upgrade header `Authorization: Bearer <token>`. No WebSocket subprotocol, cookie,
initial handshake message, or T3 SDK is required. This is **Effect RPC JSON**,
not JSON-RPC 2.0: one JSON object per WebSocket message, no newline or length prefix.
The decoder also accepts arrays; the prototype handles both response forms.
Unary calls require no stream acknowledgements. String request IDs worked.

These are the request/response envelopes that worked:

```json
{"_tag":"Request","id":"2","tag":"scheduledTasks.upsert","payload":UPSERT,"headers":[]}
{"_tag":"Exit","requestId":"2","exit":{"_tag":"Success","value":{"task":TASK}}}
{"_tag":"Request","id":"3","tag":"scheduledTasks.list","payload":{},"headers":[]}
{"_tag":"Exit","requestId":"3","exit":{"_tag":"Success","value":{"tasks":[TASK]}}}
{"_tag":"Request","id":"1","tag":"scheduledTasks.delete","payload":{"id":"36ebfc4e-7f10-4e0d-b1a6-b6e715250acd"},"headers":[]}
{"_tag":"Exit","requestId":"1","exit":{"_tag":"Success","value":{"id":"36ebfc4e-7f10-4e0d-b1a6-b6e715250acd"}}}
```

Here `UPSERT` was the following object (`T` is the full child thread ID recorded
in `evidence.json`; the full literal request is also there):

```json
{
  "id":"36ebfc4e-7f10-4e0d-b1a6-b6e715250acd",
  "title":"t3-inbox-spike",
  "prompt":"Inbox message from {{body.from}}: {{body.subject}}\n{{body.text}}\n{{body.url}}\nReply to: {{body.reply_to}}",
  "enabled":true,
  "schedule":{"type":"webhook"},
  "projectId":"9adddd03-8d9b-4aed-89a6-a5eaf778aab6",
  "threadId":"T",
  "workspaceStrategy":{"type":"root","branch":"main"},
  "modelSelection":{"instanceId":"codex","model":"gpt-6.1-sol","options":[{"id":"reasoningEffort","value":"high"}]},
  "runtimeMode":"auto",
  "interactionMode":"default"
}
```

`TASK` includes those fields plus timestamps, creator/source, execution counters,
and `webhook`. The returned schedule was
`{"type":"webhook","signature":null,"maxDeliveryAgeMinutes":null}`.
The important credential-bearing result was:

```json
{"webhook":{"path":"/api/hooks/36ebfc4e-7f10-4e0d-b1a6-b6e715250acd/U1FA…","url":null,"hasSecret":false}}
```

Thus the helper can form `http://$T3CODE_HOST:$T3CODE_PORT` + `task.webhook.path`;
it does **not** need to read the token from SQLite. `webhook.url:null` is expected
without a managed tunnel. The scoped bearer prefix was `eyJ2…`.

Derive `projectId`, `modelSelection`, `runtimeMode`, `interactionMode`, branch and
worktree from `orchestration_v2_projection_threads.payload_json` for the exact
`thread_id`. Use `{type:"existing_worktree",worktreePath,branch?}` when
`worktreePath` is present, otherwise `{type:"root",branch?}`. Required fields must
still be supplied even for an already-bound thread. The prototype implements this
and refuses absent, archived or deleted targets. No `commandId`, `createdBy`, or
`creationSource` was required; omitted creator/source defaulted to `user`/`web`.
Production should supply appropriate attribution explicitly.

**Observed delivery:** curl posted
`{"from":"spike","subject":"hello","text":"spike test, no action needed"}`
and returned **202** with
`{"deliveryId":"delivery:2b6d620b-a93f-42d9-96f6-2438f2210e58"}`.
The target acquired a durable user message containing the correctly expanded
template, with missing `url` and `reply_to` rendered empty, and a new **queued run,
ordinal 3**. No executing provider turn appeared: this research child already had
an active run. The scheduler reported `runCount:1,lastRunStatus:"succeeded"`, which
means dispatch succeeded, not that the agent handled the message. I cancelled the
test queue entry after observing it. An earlier test did the same at ordinal 2.

**Cleanup verified:** zero tasks titled `t3-inbox-spike`, zero unrevoked sessions
with that label; both test queue entries cancelled. The successful run revoked
session `72729a6b-9a8f-417a-8fce-169f3e30c190`. No full credential remains in the
prototype evidence. A first attempt had the wrong optional cleanup RPC tag;
the corrected tag is `orchestration.dispatchCommand`, with payload
`{type:"queued-run.cancel",commandId,threadId,runId}` and success `{sequence}`.

**Q2: Yes, Claude's UUID is committed before the FIRST UserPromptSubmit.** This
answer follows the installed **v0.1.0** source, rather than a newly instrumented
Claude launch:

1. `Orchestrator.ts:5023` creates a placeholder provider-thread row: its derived
   ID contains `pending:<runId>`, but `nativeThreadRef` is null.
2. `ProviderTurnStartService.ts:650` calls `session.ensureThread` for that row.
   `ClaudeAdapterV2.ts:9280` allocates a UUID; the allocator is UUIDv4 at line 731.
   This does not start the Claude process.
3. `ProviderTurnStartService.ts:828` constructs the real provider-thread payload,
   preserving the original placeholder row ID but attaching the native UUID.
   Lines 941–949 await `eventSink.writeIfRunCurrent` and require a committed write.
   `EventSink.ts:351,418` applies the projections inside the transaction; lines
   258–275 commit it before returning. `ProjectionStore.ts:2249` writes the
   provider-thread payload to SQLite.
4. Only afterwards does `ProviderTurnStartService.ts:1174` invoke `startTurn`.
   `ClaudeAdapterV2.ts:1122` supplies `{sessionId:nativeThreadId}` for a fresh CLI;
   lines 8599/8816 open it, and line 8837 offers the first user message.
5. `ProviderEventIngestor.ts:576` also persists subsequent
   `provider_thread.updated` events; the first hook does not have to wait for a
   later CLI init/session event to establish its mapping.

Use hook stdin **`session_id`**, exact match against
`payload_json.nativeThreadRef.nativeId`, with native driver **`claudeAgent`**.
Return the projection row's `thread_id`/`appThreadId`. Neither the derived
`provider_thread_id` nor `provider_session_id` is the CLI UUID. Never use cwd as
an identity: concurrent threads share it. `transcript_path` is useful only as a
secondary source for the UUID, not as a stable T3 mapping contract.
The read-only lookup prototype matched the existing Claude session from the plan
to thread `1dc6dc82-131f-4fc2-b15d-94f2141a86f6`.

**Q3: Yes, installed Codex supports both hooks.** `codex --version` reports
**codex-cli 0.163.0**; `codex features list` reports `hooks stable true`.
`/home/yair/.codex/hooks.json` already configures `UserPromptSubmit` with
`/home/yair/.local/bin/claude-time-context`, whose Codex path emits:

```json
{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"Your T3 inbox is live: …"}}
```

`SessionStart` supports the same shape with `hookEventName:"SessionStart"`.
Both inject developer context. This is documented in the fetched official
[OpenAI hooks documentation](https://learn.chatgpt.com/docs/hooks#userpromptsubmit),
including [SessionStart](https://learn.chatgpt.com/docs/hooks#sessionstart).
Configured new or changed hook definitions must be trusted under Codex's hook
trust rules; there is no need to alter the whole machine-local Codex config.

Map Codex hook stdin `session_id` (or `CODEX_THREAD_ID` in its tool environment)
with the same query, using driver **`codex`**. Verified this child's native UUID
`01a15363-95f3-77e1-9452-278712de36e8` resolves to its exact T3 child thread.
`CodexAdapterV2.ts:6566` gets that native ID from app-server `thread/start`;
the shared turn-start service persists it before starting the first turn.
**Prefer UserPromptSubmit for setup:** Codex's first SessionStart can fire inside
`thread/start`, before its response lets T3 store the mapping. Do not block that
hook waiting indefinitely for a write that depends on its completion.
Native Codex subagent hooks use the parent's session ID; T3-delegated child
threads have their own app-server thread IDs and resolve independently.

**Recommendation:** proceed with the helper design. Reuse one scoped session per
backend/user, stored mode 600, and use the small direct WS client. Resolve both
providers by exact native UUID; create/get the inbox synchronously in
UserPromptSubmit, then inject its URL on every prompt. Use a stable task ID and
serialize concurrent creation so a lost response or repeated hook cannot create
duplicates. Re-saving the same webhook task preserves its token. GC uses RPC
deletion, with read-only DB filtering of deleted/archived threads. Engine can
provision using its known T3 thread ID before the first prompt.

One design caveat: the task stores a **model snapshot**. Bound delivery passes
`active.modelSelection` to `sendToThread` (`ScheduledTaskService.ts:820`), so an
old task can request an old provider/model after a UI switch. Refresh task
configuration when the helper observes a changed thread selection; session-only
URL caching must not suppress that check. Following UI switches before another
prompt requires a synchronizer or an upstream "inherit target selection" option.

Source evidence is copied verbatim with `git show v0.1.0:<path>` under
`/tmp/t3-inbox-spike/source-v0.1.0/` (tag commit
`81493efb71e8e8244f95d3e9f71d8369654ab151`). Relevant paths relative to that root:

- `apps/server/src/ws.ts:3174`: protocol guard, authentication, JSON transport.
- `apps/server/src/auth/EnvironmentAuth.ts:1251`: bearer upgrade fallback;
  `wsTicket` is an alternative short-lived ticket, not the bearer query parameter.
- `packages/contracts/src/environment.ts:13`: protocol 2/query parameter name.
- `packages/contracts/src/scheduledTask.ts:237`: upsert fields;
  lines 317/322: mutation/delete result schemas.
- `apps/server/src/auth/RpcAuthorization.ts:116` and
  `packages/contracts/src/clientRpcPermissions.ts:44`: required scopes.
- `.repos/effect-smol/packages/effect/src/rpc/RpcMessage.ts:71,286`: wire envelopes;
  `RpcSerialization.ts:139`: plain JSON framing.

No relevant Brain TODO was closed: the parent task still owns implementation and
deployment. Credential-free debrief: `d0d17c58-fedb-47f9-9b0d-2b476043b331`.
