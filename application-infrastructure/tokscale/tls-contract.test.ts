// Run only inside the built image, --network=none. Public Node test keys only.
// This is a PostgreSQL TLS/startup mock, NOT a database or migration rehearsal.
import { test, expect } from "bun:test";
import { createServer } from "node:net";
import { createSecureContext, TLSSocket } from "node:tls";
import { readFileSync } from "node:fs";
import { sql } from "drizzle-orm";
import { getDb } from "../src/lib/db";
import { getDatabaseTlsOptions, getDatabaseCredentials } from "../src/lib/db/tls";
import { runMigrations } from "./migrate-core";

const FIXTURES = "/fixtures";
const SENTINEL = "SYNTHETIC_VERIFIED_TLS_STARTUP";
function failureChain(error: unknown): string {
  const messages: string[] = [];
  const seen = new Set<unknown>();
  while (error && !seen.has(error)) {
    seen.add(error); messages.push(String(error));
    error = typeof error === "object" ? (error as { cause?: unknown }).cause : undefined;
  }
  return messages.join("\n");
}
const secureContext = createSecureContext({
  key: readFileSync(`${FIXTURES}/agent1-key.pem`),
  cert: readFileSync(`${FIXTURES}/agent1-cert.pem`),
});

function errorPacket() {
  const payload = Buffer.from(`SFATAL\0CZX001\0M${SENTINEL}\0\0`);
  const length = Buffer.alloc(4);
  length.writeUInt32BE(payload.length + 4);
  return Buffer.concat([Buffer.from("E"), length, payload]);
}

async function mockDatabase(refuseTls = false) {
  const sockets = new Set<any>();
  const observations = { requests: 0, startups: 0 };
  const server = createServer(socket => {
    sockets.add(socket);
    socket.on("error", () => {});
    socket.once("data", request => {
      observations.requests++;
      if (request.length !== 8 || request.readUInt32BE(4) !== 80877103) {
        socket.destroy(); return;
      }
      if (refuseTls) {
        socket.write("N");
        socket.once("data", next => {
          if (next[0] === 0x16) {
            // Fatal TLS handshake_failure, so the lock does not retry a mere EOF.
            socket.end(Buffer.from([0x15, 0x03, 0x03, 0x00, 0x02, 0x02, 0x28]));
          } else {
            // A cleartext fallback is a test failure, not a successful refusal.
            observations.startups++;
            socket.end(errorPacket());
          }
        });
        return;
      }
      socket.write("S");
      const tls = new TLSSocket(socket, { isServer: true, secureContext });
      sockets.add(tls);
      tls.on("error", () => {});
      tls.once("data", () => {
        observations.startups++;
        // A recognizable PG rejection proves verified TLS + startup reached us.
        // No authentication, credentials, SQL execution or database exists here.
        tls.end(errorPacket());
      });
    });
  });
  await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
  return { observations, port: (server.address() as any).port,
    async close() { for (const socket of sockets) socket.destroy();
      await new Promise<void>(resolve => server.close(() => resolve())); } };
}

const paths = {
  async runtime(url: string) {
    (globalThis as any)._db = undefined;
    const db = getDb();
    try { await db.execute(sql`select 1`); }
    finally { await db.$client.end({ timeout: 1 }); (globalThis as any)._db = undefined; }
  },
  async migrationLock(url: string) { await runMigrations({ databaseUrl: url }); },
  async migrationChild(url: string) {
    const child = Bun.spawn(["bunx", "drizzle-kit", "migrate"], {
      cwd: "/app/packages/frontend", env: { ...process.env, DATABASE_URL: url },
      stdout: "pipe", stderr: "pipe",
    });
    const [stderr, stdout, code] = await Promise.all([
      new Response(child.stderr).text(), new Response(child.stdout).text(), child.exited,
    ]);
    if (code !== 0) throw new Error(stderr + stdout);
  },
};

for (const [name, invoke] of Object.entries(paths)) {
  for (const scenario of ["trusted", "wrong-ca", "wrong-hostname", "plaintext-refused"]) {
    test(`${name}: ${scenario}`, async () => {
      const mock = await mockDatabase(scenario === "plaintext-refused");
      process.env.DATABASE_SSL = "verify-full";
      process.env.DATABASE_CA_FILE = `${FIXTURES}/${scenario === "wrong-ca" ? "ca2" : "ca1"}-cert.pem`;
      const host = scenario === "wrong-hostname" ? "wrongname" : "agent1";
      const url = `postgresql://synthetic:PUBLIC_TEST_VALUE@${host}:${mock.port}/synthetic`;
      process.env.DATABASE_URL = url;
      delete process.env.NODE_TLS_REJECT_UNAUTHORIZED;
      let failure = "";
      try { await invoke(url); } catch (error) { failure = failureChain(error); }
      finally { await mock.close(); }
      expect(mock.observations.requests).toBeGreaterThan(0);
      expect(failure.length).toBeGreaterThan(0);
      if (scenario === "trusted") {
        expect(failure).toContain(SENTINEL);
        expect(mock.observations.startups).toBeGreaterThan(0);
      } else {
        expect(failure).not.toContain(SENTINEL);
        expect(mock.observations.startups).toBe(0);
      }
    }, 15000);
  }
}

test("no insecure modes, URL overrides, IP bypass or process override", () => {
  process.env.DATABASE_CA_FILE = `${FIXTURES}/ca1-cert.pem`;
  for (const mode of [undefined, "require", "false", "disable", "prefer", "true"]) {
    if (mode === undefined) delete process.env.DATABASE_SSL;
    else process.env.DATABASE_SSL = mode;
    expect(() => getDatabaseTlsOptions("postgresql://agent1/test")).toThrow();
  }
  process.env.DATABASE_SSL = "verify-full";
  for (const url of ["postgresql://agent1/test?sslmode=disable", "postgresql://127.0.0.1/test", "http://agent1/test"]) {
    expect(() => getDatabaseTlsOptions(url)).toThrow();
  }
  const credentials = getDatabaseCredentials("postgresql://public%2Buser:PUBLIC%40VALUE@agent1:5433/synthetic");
  expect(credentials.user).toBe("public+user");
  expect(credentials.password).toBe("PUBLIC@VALUE");
  expect(credentials.port).toBe(5433);
  expect(credentials.ssl.rejectUnauthorized).toBe(true);
  expect("url" in credentials).toBe(false);
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";
  expect(() => getDatabaseTlsOptions("postgresql://agent1/test")).toThrow();
  delete process.env.NODE_TLS_REJECT_UNAUTHORIZED;
});
