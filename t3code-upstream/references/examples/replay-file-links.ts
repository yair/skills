// Example from PR #20861: replay every thread in a T3 database through the
// relative-link resolver, with and without the change, and check targets on
// disk. Adapt the resolver calls for another fix; keep the shape: read-only,
// one tally of before/after outcomes, details only for links that changed.
//
// Run it on a COPY of the database, taken with SQLite's backup so the WAL is
// included (sqlite3 -readonly ~/.t3/userdata/<db> ".backup /tmp/copy.sqlite"), with
// `node --experimental-strip-types replay.ts /tmp/copy.sqlite`, then delete
// the copy. Report only aggregate counts in a PR, never paths or thread text.
//
// SCHEMA: this reads the V1 `state.sqlite` (projection_threads,
// projection_thread_activities, projection_thread_messages), frozen since
// 0.1.0. Current threads live in `statev2.sqlite`; inspect its tables with
// `sqlite3 -readonly COPY .tables` and adapt the queries before trusting
// results. Imports point at the checkout's TypeScript sources directly.
import { DatabaseSync } from "node:sqlite";
import { existsSync } from "node:fs";
import {
  extractInlineCodeSpans,
  extractMarkdownLinkHrefs,
  inlineCodeFilePathCandidate,
  isRelativeFilePath,
  parseMarkdownFileLink,
  resolveMarkdownFileLinkTarget,
} from "/home/yair/w/t3code/packages/shared/src/markdownLinks.ts";
import { splitFilePathPosition } from "/home/yair/w/t3code/packages/shared/src/fileLinks.ts";
import {
  buildThreadFilePathIndex,
  threadFilePaths,
} from "/home/yair/w/t3code/packages/shared/src/threadFilePaths.ts";

const db = new DatabaseSync(process.argv[2]!, { readOnly: true });
const threads = db
  .prepare(
    `select t.thread_id id, coalesce(t.worktree_path, p.workspace_root) cwd from projection_threads t
     left join projection_projects p on p.project_id = t.project_id`,
  )
  .all() as { id: string; cwd: string | null }[];

function toItem(payload: any): any | null {
  const data = payload.data ?? {};
  const input = data.input ?? {};
  switch (payload.itemType) {
    case "command_execution":
      return typeof input.command === "string" ? { type: "command_execution", input: input.command } : null;
    case "file_change":
      return typeof input.file_path === "string" ? { type: "file_change", fileName: input.file_path } : null;
    case "image_view":
      return { type: "dynamic_tool", viewedImagePath: input.file_path, input };
    case "dynamic_tool_call":
      return { type: "dynamic_tool", input };
    default:
      return null;
  }
}

const exists = (target: string) => existsSync(splitFilePathPosition(target).path);
const tally: Record<string, number> = {};
const changes: string[] = [];
let relative = 0;
for (const thread of threads) {
  const items = (
    db
      .prepare(
        `select payload_json from projection_thread_activities where thread_id = ? and kind = 'tool.completed' order by created_at`,
      )
      .all(thread.id) as { payload_json: string }[]
  ).flatMap((row) => {
    const item = toItem(JSON.parse(row.payload_json));
    return item ? [item] : [];
  });
  const index = buildThreadFilePathIndex(threadFilePaths(items, thread.cwd));
  const messages = db
    .prepare(`select text from projection_thread_messages where thread_id = ? and role = 'assistant'`)
    .all(thread.id) as { text: string }[];
  const cwd = thread.cwd ?? undefined;
  const seen = new Set<string>();
  for (const { text } of messages) {
    const references = [
      ...extractMarkdownLinkHrefs(text),
      ...extractInlineCodeSpans(text).flatMap((span) => {
        const candidate = inlineCodeFilePathCandidate(span);
        return candidate ? [candidate] : [];
      }),
    ];
    for (const reference of references) {
      const target = parseMarkdownFileLink(reference);
      if (!target || !isRelativeFilePath(target.path)) continue;
      if (seen.has(reference)) continue;
      seen.add(reference);
      relative += 1;
      const before = resolveMarkdownFileLinkTarget(reference, cwd, cwd);
      const bound = resolveMarkdownFileLinkTarget(reference, cwd, cwd, index);
      // Tally the resolver's raw proposal too. The gate below copies the chip's
      // own rule (switch only when the join is missing and the candidate
      // exists), so the gated tally alone cannot show the moves it prevents.
      if (bound && bound !== before) {
        const raw = `raw: ${before && exists(before) ? "old exists" : "old missing"} -> ${exists(bound) ? "new exists" : "new missing"}`;
        tally[raw] = (tally[raw] ?? 0) + 1;
      }
      const after = bound && bound !== before && (!before || (!exists(before) && exists(bound))) ? bound : before;
      if (before === after) {
        tally[`unchanged, ${before && exists(before) ? "exists" : "missing"}`] =
          (tally[`unchanged, ${before && exists(before) ? "exists" : "missing"}`] ?? 0) + 1;
        continue;
      }
      const kind = `${before && exists(before) ? "old exists" : "old missing"} -> ${after && exists(after) ? "new exists" : "new missing"}`;
      tally[kind] = (tally[kind] ?? 0) + 1;
      changes.push(`[${kind}] ${thread.id.slice(0, 8)} ${reference}\n    before ${before}\n    after  ${after}`);
    }
  }
}
console.log(`threads ${threads.length}, distinct relative file references ${relative}`);
console.log(tally);
console.log(changes.join("\n"));
