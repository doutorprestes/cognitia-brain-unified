import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { mkdir, readFile, writeFile } from "node:fs/promises";

import initSqlJs, { Database, SqlJsStatic } from "sql.js";

import { Opportunity } from "../types.js";
import { createLogger } from "./logger.js";

const logger = createLogger("database");
const require = createRequire(import.meta.url);

const DATA_DIR = process.env.DATA_DIR || ".";
export const DATABASE_FILE = join(DATA_DIR, "data", "grantwatch.sqlite");

export type OpportunityDecision = "unreviewed" | "apply" | "watch" | "dismiss" | "favorite";

type StoredOpportunityRow = {
  key: string;
  title: string;
  date: string;
  link: string;
  snippet: string;
  source: string;
  track: string;
  score: number;
  priority: string;
  payload_json: string;
  first_seen_at: string;
  last_seen_at: string;
  status: string;
  decision: OpportunityDecision;
  notes: string | null;
};

function nowIso(): string {
  return new Date().toISOString();
}

export function opportunityKey(item: { title: string; source: string; link: string }): string {
  // Removida a data da chave para permitir rastreamento de mudanças no mesmo edital
  return `${item.source}||${item.link}||${item.title}`;
}

async function loadSql(): Promise<SqlJsStatic> {
  const sqlJsPath = require.resolve("sql.js");
  const distDir = dirname(sqlJsPath);
  return initSqlJs({
    locateFile: (file) => join(distDir, file)
  });
}

async function openDatabase(path = DATABASE_FILE): Promise<Database> {
  const SQL = await loadSql();
  try {
    const file = await readFile(path);
    return new SQL.Database(file);
  } catch {
    return new SQL.Database();
  }
}

async function persistDatabase(db: Database, path = DATABASE_FILE): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, Buffer.from(db.export()));
}

function migrate(db: Database): void {
  db.run(`
    PRAGMA user_version = 1;

    CREATE TABLE IF NOT EXISTS runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      started_at TEXT NOT NULL,
      finished_at TEXT,
      status TEXT NOT NULL,
      raw_count INTEGER NOT NULL DEFAULT 0,
      qualified_count INTEGER NOT NULL DEFAULT 0,
      fresh_count INTEGER NOT NULL DEFAULT 0,
      alert_count INTEGER NOT NULL DEFAULT 0,
      error_message TEXT
    );

    CREATE TABLE IF NOT EXISTS opportunities (
      key TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      date TEXT NOT NULL,
      link TEXT NOT NULL,
      snippet TEXT NOT NULL,
      source TEXT NOT NULL,
      track TEXT NOT NULL,
      score INTEGER NOT NULL,
      priority TEXT NOT NULL,
      payload_json TEXT NOT NULL,
      first_seen_at TEXT NOT NULL,
      last_seen_at TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'active',
      decision TEXT NOT NULL DEFAULT 'unreviewed',
      notes TEXT
    );

    CREATE TABLE IF NOT EXISTS opportunity_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      opportunity_key TEXT NOT NULL,
      event_type TEXT NOT NULL,
      event_at TEXT NOT NULL,
      detail_json TEXT,
      FOREIGN KEY (opportunity_key) REFERENCES opportunities(key)
    );

    CREATE INDEX IF NOT EXISTS idx_opportunities_last_seen ON opportunities(last_seen_at);
    CREATE INDEX IF NOT EXISTS idx_opportunities_score ON opportunities(score);
    CREATE INDEX IF NOT EXISTS idx_opportunity_events_key ON opportunity_events(opportunity_key);
  `);
}

function rowFromStatement(stmt: any): StoredOpportunityRow {
  const row = stmt.getAsObject();
  return row as StoredOpportunityRow;
}

export async function loadPreviousFromDatabase(path = DATABASE_FILE): Promise<Opportunity[]> {
  const db = await openDatabase(path);
  try {
    migrate(db);
    const stmt = db.prepare("SELECT payload_json FROM opportunities WHERE status = 'active'");
    const items: Opportunity[] = [];
    while (stmt.step()) {
      const row = stmt.getAsObject() as { payload_json: string };
      items.push(JSON.parse(row.payload_json) as Opportunity);
    }
    stmt.free();
    logger.info({ count: items.length }, "Loaded previous items from SQLite");
    return items;
  } finally {
    db.close();
  }
}

export async function saveRunToDatabase(input: {
  current: Opportunity[];
  rawCount: number;
  freshCount: number;
  alertCount: number;
  startedAt?: string;
  path?: string;
}): Promise<void> {
  const db = await openDatabase(input.path ?? DATABASE_FILE);
  const seenAt = nowIso();
  const startedAt = input.startedAt ?? seenAt;

  try {
    migrate(db);
    db.run("BEGIN TRANSACTION");
    try {
      const run = db.prepare(
        "INSERT INTO runs (started_at, finished_at, status, raw_count, qualified_count, fresh_count, alert_count) VALUES (?, ?, ?, ?, ?, ?, ?)"
      );
      run.run([startedAt, seenAt, "success", input.rawCount, input.current.length, input.freshCount, input.alertCount]);
      run.free();

      const currentKeys: string[] = [];
      for (const item of input.current) {
        const key = opportunityKey(item);
        currentKeys.push(key);
        const existingStmt = db.prepare("SELECT * FROM opportunities WHERE key = ?");
        existingStmt.bind([key]);
        const existing = existingStmt.step() ? rowFromStatement(existingStmt) : null;
        existingStmt.free();

        if (!existing) {
          db.run(
            `INSERT INTO opportunities (
              key, title, date, link, snippet, source, track, score, priority, payload_json, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
            [
              key,
              item.title,
              item.date,
              item.link,
              item.snippet,
              item.source,
              item.track,
              item.score,
              item.priority,
              JSON.stringify(item),
              seenAt,
              seenAt
            ]
          );
          db.run(
            "INSERT INTO opportunity_events (opportunity_key, event_type, event_at, detail_json) VALUES (?, ?, ?, ?)",
            [key, "first_seen", seenAt, JSON.stringify({ score: item.score, priority: item.priority })]
          );
          continue;
        }

        const changedDeadline = existing.date !== item.date;
        const changedScore = existing.score !== item.score;
        const changedSnippet = existing.snippet !== item.snippet;

        db.run(
          `UPDATE opportunities
           SET title = ?, date = ?, link = ?, snippet = ?, source = ?, track = ?, score = ?, priority = ?,
               payload_json = ?, last_seen_at = ?, status = 'active'
           WHERE key = ?`,
          [
            item.title,
            item.date,
            item.link,
            item.snippet,
            item.source,
            item.track,
            item.score,
            item.priority,
            JSON.stringify(item),
            seenAt,
            key
          ]
        );

        if (changedDeadline || changedScore || changedSnippet) {
          const { diffChars } = await import("diff");
          const snippetDiff = changedSnippet ? diffChars(existing.snippet, item.snippet) : undefined;

          db.run(
            "INSERT INTO opportunity_events (opportunity_key, event_type, event_at, detail_json) VALUES (?, ?, ?, ?)",
            [
              key,
              "updated",
              seenAt,
              JSON.stringify({
                previous_date: existing.date,
                current_date: item.date,
                previous_score: existing.score,
                current_score: item.score,
                content_changed: changedSnippet,
                diff: snippetDiff
              })
            ]
          );
        }
      }

      if (currentKeys.length > 0) {
        const placeholders = currentKeys.map(() => "?").join(", ");
        db.run(
          `UPDATE opportunities SET status = 'stale' WHERE status = 'active' AND key NOT IN (${placeholders})`,
          currentKeys
        );
      } else {
        db.run("UPDATE opportunities SET status = 'stale' WHERE status = 'active'");
      }

      db.run("COMMIT");
    } catch (error) {
      db.run("ROLLBACK");
      throw error;
    }

    await persistDatabase(db, input.path ?? DATABASE_FILE);
    logger.info({ count: input.current.length }, "Saved run to SQLite");
  } finally {
    db.close();
  }
}

export async function loadOpportunityDecisions(path = DATABASE_FILE): Promise<Map<string, { decision: OpportunityDecision; notes?: string }>> {
  const db = await openDatabase(path);
  try {
    migrate(db);
    const stmt = db.prepare("SELECT key, decision, notes FROM opportunities WHERE decision <> 'unreviewed' OR notes IS NOT NULL");
    const decisions = new Map<string, { decision: OpportunityDecision; notes?: string }>();
    while (stmt.step()) {
      const row = stmt.getAsObject() as { key: string; decision: OpportunityDecision; notes?: string | null };
      decisions.set(row.key, { decision: row.decision, notes: row.notes ?? undefined });
    }
    stmt.free();
    return decisions;
  } finally {
    db.close();
  }
}

export async function loadOpportunityEvents(path = DATABASE_FILE): Promise<Map<string, any[]>> {
  const db = await openDatabase(path);
  try {
    migrate(db);
    const stmt = db.prepare("SELECT opportunity_key, event_type, event_at, detail_json FROM opportunity_events ORDER BY event_at DESC");
    const eventsMap = new Map<string, any[]>();
    while (stmt.step()) {
      const row = stmt.getAsObject() as { opportunity_key: string; event_type: string; event_at: string; detail_json: string };
      const list = eventsMap.get(row.opportunity_key) || [];
      list.push({
        type: row.event_type,
        at: row.event_at,
        detail: row.detail_json ? JSON.parse(row.detail_json) : null
      });
      eventsMap.set(row.opportunity_key, list);
    }
    stmt.free();
    return eventsMap;
  } finally {
    db.close();
  }
}

export async function updateOpportunityDecision(input: {
  keyOrUrl: string;
  decision: OpportunityDecision;
  notes?: string;
  path?: string;
}): Promise<boolean> {
  const db = await openDatabase(input.path ?? DATABASE_FILE);
  try {
    migrate(db);
    const matched = db.prepare("SELECT key FROM opportunities WHERE key = ? OR link = ? LIMIT 1");
    matched.bind([input.keyOrUrl, input.keyOrUrl]);
    const key = matched.step() ? (matched.getAsObject() as { key: string }).key : null;
    matched.free();
    if (!key) {
      return false;
    }

    const updatedAt = nowIso();
    db.run(
      "UPDATE opportunities SET decision = ?, notes = COALESCE(?, notes) WHERE key = ?",
      [input.decision, input.notes ?? null, key]
    );
    db.run(
      "INSERT INTO opportunity_events (opportunity_key, event_type, event_at, detail_json) VALUES (?, ?, ?, ?)",
      [key, "decision_changed", updatedAt, JSON.stringify({ decision: input.decision, notes: input.notes })]
    );
    await persistDatabase(db, input.path ?? DATABASE_FILE);
    return true;
  } finally {
    db.close();
  }
}
