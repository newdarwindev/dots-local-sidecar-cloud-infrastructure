// Real PostgreSQL qualification. Synthetic fixtures, isolated Docker namespace only.
import { strict as assert } from "node:assert";
import { sql } from "drizzle-orm";
import postgres from "postgres";
import { getDb } from "../src/lib/db";
import { getDatabaseTlsOptions } from "../src/lib/db/tls";
import { runMigrations } from "./migrate-core";

const url = process.env.DATABASE_URL!;
const cwd = "/app/packages/frontend";
const admin = postgres(url, { max: 1, ssl: getDatabaseTlsOptions(url) });
function pass(name: string) { console.log(`PASS ${name}`); }
function causes(error: any): string {
  return error ? String(error) + " " + (error.code ?? "") + " " + causes(error.cause) : "";
}
async function migrate() { await runMigrations({ databaseUrl: url, cwd }); }
async function child(env: Record<string, string | undefined>) {
  const p = Bun.spawn(["bunx", "drizzle-kit", "migrate"], {
    cwd, env: { ...process.env, ...env }, stdout: "pipe", stderr: "pipe",
  });
  const [out, err, code] = await Promise.all([
    new Response(p.stdout).text(), new Response(p.stderr).text(), p.exited,
  ]);
  if (code) throw new Error(out + err);
}
async function runtime() {
  (globalThis as any)._db = undefined;
  const db = getDb();
  try { await db.execute(sql`select 1`); }
  finally { await db.$client.end({ timeout: 1 }); (globalThis as any)._db = undefined; }
}
async function main() {
  const mode = process.argv[2];
  if (mode === "baseline") {
    await migrate();
    const [initial] = await admin`select count(*)::int as n from drizzle.__drizzle_migrations`;
    assert.equal(initial.n, 33);
    await Promise.all([migrate(), migrate()]);
    const [after] = await admin`select count(*)::int as n from drizzle.__drizzle_migrations`;
    assert.equal(after.n, initial.n);
    pass("33 migrations, repeated and concurrent migration idempotence");
    await runtime();
    const [tls] = await admin`select ssl from pg_stat_ssl where pid=pg_backend_pid()`;
    assert.equal(tls.ssl, true);
    pass("runtime and migration paths use real PostgreSQL TLS");
    await admin`create table synthetic_qualification (id integer primary key, value text not null)`;
    const db = getDb();
    await Promise.all(Array.from({ length: 100 }, (_, i) =>
      db.execute(sql`insert into synthetic_qualification values (${i}, 'synthetic-only')`)));
    const [count] = await admin`select count(*)::int as n from synthetic_qualification`;
    assert.equal(count.n, 100);
    await db.$client.end({ timeout: 1 });
    pass("100 concurrent synthetic writes through runtime singleton");
  } else if (mode === "negative") {
    for (const scenario of ["wrong-ca", "wrong-hostname"]) {
      const env = {
        DATABASE_URL: scenario === "wrong-hostname" ? url.replace("agent1", "wrongname") : url,
        DATABASE_CA_FILE: `/fixtures/${scenario === "wrong-ca" ? "ca2" : "ca1"}-cert.pem.fixture`,
      };
      const original = { DATABASE_URL: process.env.DATABASE_URL, DATABASE_CA_FILE: process.env.DATABASE_CA_FILE };
      Object.assign(process.env, env);
      try {
        for (const [name, invoke] of Object.entries({
          runtime,
          migrationLock: () => runMigrations({ databaseUrl: env.DATABASE_URL, cwd }),
          migrationChild: () => child(env),
        })) {
          await assert.rejects(invoke, error => /cert|verify|issuer|altname|hostname|self.signed/i.test(causes(error)));
          pass(`${name} rejects ${scenario} against real PostgreSQL`);
        }
      } finally { Object.assign(process.env, original); }
    }
  } else if (mode === "plaintext") {
    for (const [name, invoke] of Object.entries({
      runtime, migrationChild: () => child({}),
    })) {
      await assert.rejects(invoke, error => /ssl|tls/i.test(causes(error)));
      pass(`${name} rejects real PostgreSQL with TLS disabled`);
    }
    // The upstream lock wrapper retries CONNECTION_CLOSED even when caused by
    // TLS refusal. Observe fail-closed behavior for a bounded window, not all
    // 60 retries; this does not claim fail-fast refusal by that wrapper.
    const p = Bun.spawn(["bun", "scripts/migrate-docker.ts"], {
      cwd, env: process.env, stdout: "pipe", stderr: "pipe",
    });
    const output = new Response(p.stdout).text();
    const errors = new Response(p.stderr).text();
    await Bun.sleep(10000);
    assert.equal(p.exitCode, null, "expected upstream TLS-refusal retry loop");
    p.kill("SIGTERM"); await p.exited;
    const transcript = await output + await errors;
    console.log(transcript);
    assert.match(transcript, /could not reach DB to acquire migration advisory lock/);
    assert.doesNotMatch(transcript, /ok - acquired advisory lock|migrations applied successfully/);
    pass("migration lock stays fail-closed during bounded TLS-refusal retry observation (not fail-fast)");
  } else if (mode === "reconnect") {
    const db = getDb();
    await db.execute(sql`select 1`);
    await Bun.write("/tmp/reconnect-ready", "ready");
    while (!(await Bun.file("/tmp/reconnect-resume").exists())) await Bun.sleep(100);
    let recovered = false;
    for (let i = 0; i < 15; i++) {
      try {
        const rows = await db.execute(sql`select count(*)::int as n from synthetic_qualification`);
        assert.equal(rows[0].n, 100); recovered = true; break;
      } catch { await Bun.sleep(500); }
    }
    assert.equal(recovered, true);
    await db.$client.end({ timeout: 1 });
    pass("existing runtime pool reconnects after PostgreSQL process restart; 100 rows retained");
  } else if (mode === "retry") {
    await migrate();
    pass("migration lock acquisition retries database interruption");
  } else if (mode === "child-retry") {
    // Block Drizzle's journal query, then terminate only that synthetic client.
    const blocker = postgres(url, { max: 1, ssl: getDatabaseTlsOptions(url) });
    let release!: () => void;
    let locked!: () => void;
    const ready = new Promise<void>(resolve => { locked = resolve; });
    const gate = new Promise<void>(resolve => { release = resolve; });
    const holding = blocker.begin(async tx => {
      await tx`lock table drizzle.__drizzle_migrations in access exclusive mode`;
      locked(); await gate;
    });
    await ready;
    const migration = migrate();
    let interrupted = false;
    try {
      for (let i = 0; i < 150; i++) {
        const candidates = await admin`select pid from pg_stat_activity
          where pid <> pg_backend_pid() and wait_event_type='Lock'
          and query ilike '%__drizzle_migrations%' and query not ilike 'lock table%'`;
        if (candidates.length) {
          await admin`select pg_terminate_backend(${candidates[0].pid})`;
          interrupted = true; break;
        }
        await Bun.sleep(100);
      }
    } finally { release(); await holding; await blocker.end(); }
    assert.equal(interrupted, true, "real migration child must have been interrupted");
    await migration;
    const [count] = await admin`select count(*)::int as n from drizzle.__drizzle_migrations`;
    assert.equal(count.n, 33);
    pass("terminated real migration child retries successfully without duplicate journal rows");
  } else throw new Error(`Unknown mode: ${mode}`);
}
try { await main(); } finally { await admin.end({ timeout: 1 }); }
