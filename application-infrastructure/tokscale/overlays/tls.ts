// Reviewed private-hub overlay. No cleartext or unauthenticated TLS mode.
import { readFileSync } from "node:fs";
import { isAbsolute } from "node:path";
import { isIP } from "node:net";
import { checkServerIdentity, type ConnectionOptions } from "node:tls";

export function getDatabaseTlsOptions(databaseUrl: string): ConnectionOptions {
  if (process.env.DATABASE_SSL !== "verify-full") {
    throw new Error("DATABASE_SSL must be verify-full");
  }
  if (process.env.NODE_TLS_REJECT_UNAUTHORIZED !== undefined &&
      process.env.NODE_TLS_REJECT_UNAUTHORIZED !== "1") {
    throw new Error("TLS verification override forbidden");
  }
  const url = new URL(databaseUrl);
  if (!["postgres:", "postgresql:"].includes(url.protocol) || !url.hostname ||
      isIP(url.hostname) || !/^[a-zA-Z0-9.-]+$/.test(url.hostname) || url.search || url.hash) {
    throw new Error("Database URL requires one DNS hostname and no query/fragment overrides");
  }
  const caFile = process.env.DATABASE_CA_FILE;
  if (!caFile || !isAbsolute(caFile)) {
    throw new Error("DATABASE_CA_FILE must reference an absolute trusted CA file");
  }
  const ca = readFileSync(caFile, "utf8");
  if (!ca.includes("-----BEGIN CERTIFICATE-----")) {
    throw new Error("Trusted database CA certificate missing");
  }
  return { ca, rejectUnauthorized: true, servername: url.hostname,
           checkServerIdentity };
}

// drizzle-kit 0.30.6 discards separate ssl options when `url` is present.
// Structured credentials keep the exact same verified TLS options in its driver.
export function getDatabaseCredentials(databaseUrl: string) {
  const ssl = getDatabaseTlsOptions(databaseUrl);
  const url = new URL(databaseUrl);
  if (!url.pathname || url.pathname === "/") throw new Error("Database name required");
  return {
    host: url.hostname, port: Number(url.port || "5432"),
    database: decodeURIComponent(url.pathname.slice(1)),
    user: decodeURIComponent(url.username), password: decodeURIComponent(url.password),
    ssl,
  };
}
