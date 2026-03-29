import { createClient, type Client } from "@libsql/client";
import path from "path";

let _client: Client | null = null;

export function getDb(): Client {
  if (_client) return _client;

  const url = process.env.TURSO_DATABASE_URL;
  const authToken = process.env.TURSO_AUTH_TOKEN;

  if (url?.startsWith("libsql://")) {
    // Remote Turso
    _client = createClient({ url, authToken });
  } else {
    // Local SQLite — resolve relative to project root
    const home = process.env.HOME ?? process.env.USERPROFILE ?? "/tmp";
    const dbPath =
      url?.replace(/^file:/, "") ??
      path.join(home, ".prover-poslance", "tmp", "parliament_data.db");
    _client = createClient({ url: `file:${dbPath}` });
  }

  return _client;
}

export type Row = Record<string, unknown>;

export async function query<T = Row>(
  sql: string,
  args: (string | number | null)[] = []
): Promise<T[]> {
  const db = getDb();
  const result = await db.execute({ sql, args });
  return result.rows.map((row) =>
    Object.fromEntries(result.columns.map((col, i) => [col, row[i]]))
  ) as unknown as T[];
}
