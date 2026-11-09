# Desktop dashboards beside Conky

An optional Linux/X11 login-session launcher for the minimal WebKit/GTK browser
[surf](https://surf.suckless.org/). It creates borderless desktop-type windows,
below applications and Conky, sticky across workspaces and absent from the taskbar
and pager. It reserves an icon column and top-panel clearance, follows monitor
changes and leaves a 42-pixel gap before the actual `ConkyDashboard` window.
Without Conky it uses the monitor's available width with a right margin.

This is an explicitly installed desktop utility, separate from either cluster
bootstrap. Installing it is a persistent login-startup change. Its default
configuration is inert: no cluster access, forwarding, accounts or deployments.
Configure and start connections only within the owner's authorized scope.

## Install and configure

On a Debian-family X11/XFCE host, install `surf`, `python3-xlib`, `x11-xserver-utils`
and Python 3 using the host's package manager. GTK/WebKit dependencies are managed
by the distribution. Keep WebKit updated; a small browser shell does not guarantee
small page memory use. Run `sh desktop-dashboard/install.sh` from this checkout.
The installer preserves an existing private config and writes:

- `~/.local/lib/desktop-dashboard/dashboard.py` and `~/.local/bin/desktop-dashboard`;
- `~/.config/autostart/desktop-dashboard.desktop`, with a 12-second login delay;
- an application-menu entry and an initially inert private config at
  `~/.config/desktop-dashboard/config.json`.

The installed implementation includes `live_status.py` and `health_otel.py`;
neither enables collection or export in the default configuration.

Edit the private JSON before starting. `links` contains `id`, `name`, optional
`description` and either a credential-free HTTPS `url`, an authorized `forward`
ID with relative `path`, or an inactive `status`. `start` selects a link ID or
`home`. The generated home page lists connection status and bookmarks without
running staged services. Do not put passwords, tokens or credential-bearing URLs
in this configuration, the repository or process arguments.

To keep configured dashboards side by side, add a `panes` array. For example,
after configuring the two referenced links:

```json
"panes": [
  {"link": "langfuse", "weight": 70, "langfuse_refresh_ms": 30000},
  {"link": "homarr", "weight": 30}
]
```

One to three distinct links (or `home`) are supported. Positive `weight` values
divide the existing available area, separated by 16 pixels; small displays use
a vertical stack when necessary. Optional `zoom` is 0.5–2. Without `panes`, the
existing `start` setting selects one window. Closed panes restart after 15 seconds.
Conky's bounds and configuration are preserved.

For a Langfuse link to `/project/<project-id>/traces`, `langfuse_refresh_ms` sets
its native table refresh and collapses the navigation sidebar. Supported values
are 30000, 60000, 300000 and 900000. The generated surf script applies only to
that exact origin and project; it reloads once per browser session when changing
preferences. Browser storage is enabled for this pane. Refreshing a table does
not itself enroll a telemetry source or create observations.

An optional `cluster` object selects an existing kubectl `context`, the observed
`system_namespace_uid` of `kube-system`, and a `namespace_uids` mapping. Each
`forwards` item names an `id`, `namespace`, `service`, `local_port` and
`remote_port`. Use independently verified identities from the intended cluster;
the launcher reads namespace UIDs only and never copies kubeconfig credentials.
Private configuration and identity pins belong outside this public repository.

Connections always bind **127.0.0.1**, belong to the login-session supervisor and
stop with it. They do not create Ingress, NodePort, LAN listeners or public tunnels.
Changed/unavailable cluster or namespace identities, occupied local ports and
failed upstream checks keep links inactive; retries occur at 30-second intervals.
Only explicitly named services are forwarded. Kubectl uses the existing user's
credentials and their existing privileges; this utility does not reduce them.

Loopback forwarding is plain HTTP to the existing service, **not** an authenticated
HTTPS gateway or a multiuser isolation boundary. Other local users can reach its
TCP ports. Service sign-in/onboarding remains the service's responsibility. A
host's authenticated-gateway policy must explicitly permit this narrower local
session route before enabling it. Never infer account creation, certificates,
OAuth grants, production access or real-data activation from desktop installation.

## Use and recovery

Run `desktop-dashboard` now or let XFCE start it after login. The single-instance
lock prevents duplicate browsers/forwards. From the focused dashboard,
**Ctrl+Alt+Shift+Home** opens the local dashboard hub; the application-menu entry and
`desktop-dashboard --home` open the hub in the primary pane. The shortcut applies
to the focused pane. Surf's **Ctrl+h** goes back and **Ctrl+r**
reloads. Configure Homarr App links to open in the same window; popup-created
browser windows are ordinary drill-down windows, outside this supervisor's layout.

`desktop-dashboard --status` reports the last observed connection sample and time
and checks the supervisor lock. It alone does not prove browser or UI health.
`desktop-dashboard --stop` stops
all owned panes, the overview and forwards. Disable later login startup by setting
`Hidden=true` in `~/.config/autostart/desktop-dashboard.desktop`, then stop it.
Re-enable by removing that line. No reboot is needed.

State is under `~/.local/state/desktop-dashboard/`: append-only launcher/forward
logs, generated `status.json` and observed pane geometry in `panes.json`.
The generated hub and private cookie databases
are under `~/.surf/desktop-dashboard/`, within surf's distribution AppArmor
allowlist; no AppArmor relaxation is required. State files use owner-only
permissions and are never source artifacts. Browser cookies can confer access;
preserve their privacy. The runtime control socket and
lock use `$XDG_RUNTIME_DIR/desktop-dashboard` when available. A restart preserves
existing logs and cookies. Uninstallation may remove the launcher and two desktop
entries, but must preserve any histories, service data, credentials and receipts.

The first pane retains `cookies.txt`. Additional panes use `cookies-<link>.txt`,
seeded once from the first pane's dedicated cookie file and preserved thereafter.
Each pane can retain its own service session without concurrent cookie-file writes.

Inspect geometry with `xwininfo` and state/type with `xprop`. Verify icon/panel
clearance, Conky's unchanged bounds, stacking under an ordinary application,
workspace switching, duplicate launch, Home navigation, forward recovery and
stop/cleanup on the actual host. Window-manager behavior is a live acceptance
check; offline tests do not establish it.

## Optional live workload panel

An explicitly enabled `overview` object adds a read-only loopback HTTP child,
owned by the same desktop supervisor. Select `port`, an identity-pinned
`namespace`, a display `title`, and optional `storage` entries with `name`/`path`.
`refresh_seconds` defaults to 15 and must be 5–300. Its port must differ from the
configured service forwards. The default example leaves this collector disabled.

The collector checks cluster/namespace UIDs on every refresh, then queries only
nodes, pods and PVC metadata. It displays selected workload readiness, restarts,
volume bindings, HTTP health, host available memory and explicitly selected
filesystem capacity. It reuses CPU-only samples from the existing Conky history
without changing Conky. Missing data is unknown, stale data is marked stale, and
connection failures stay visible. No Kubernetes logs, Secret objects, addresses,
environment variables, serials or conversation contents enter its browser JSON.

The page is available at `/` or `/embed`, with JSON at `/api/status`. It has no
write routes or arbitrary file serving; unexpected Host headers are rejected.
It may be embedded in Homarr at `http://127.0.0.1:17575`; its CSP permits that
origin and itself only. Create an iframe item with the exact local `/embed` URL,
no camera/microphone/location/payment permissions, and enough grid rows for the
table. Use current-tab App navigation. Remove irrelevant first-run sample widgets
from the new board after retaining its configuration for recovery.

A separately authorized **synthetic** Langfuse verification project may supply
an optional `verification_credentials` path in the private overview configuration.
Only its numeric observation/trace counts are returned; API credentials stay in
the backend and are never embedded in browser code. The collector authenticates
only when the supervisor reports its Langfuse forward owned and healthy. The
count covers up to the latest 100 observations and is labeled synthetic.
Real workload readiness and synthetic tracing tests are separate observations.

### Optional live health traces

After the owner explicitly selects **live local dashboard health checks**, create
a separate Langfuse project and project-scoped API key through the service's
supported flows. Keep verification fixtures in their synthetic project. Store
`public_key`, `secret_key` and `project_id` in an owner-only local JSON file, and
set `overview.live_health_credentials` to its absolute path. This requires an
explicitly configured, owned `langfuse` forward. There is no default enrollment,
account creation or key generation at startup.

Each overview sample then exports one real collection span and child spans for
the actual owned HTTP service checks, using their measured times, HTTP status
and health. The reconstructed OTLP envelope contains only these fields, service
labels, `local-desktop` environment and `synthetic=false`; it excludes prompts,
responses, histories, log contents, host identities and arbitrary snapshot data.
API keys remain in the Python child, outside browser code. Export pauses when
the supervisor's Langfuse connection is not owned and healthy.

The overview shows accepted spans, errors and skipped batches in `/api/status`,
with a visible feed status. Counters reset with the overview process. HTTP
acceptance is separate from persisted-data verification. There is no durable
queue or replay guarantee: unavailable destinations and uncertain deliveries
can leave gaps, and this diagnostic stream is not a complete audit record.

Langfuse receives these traces directly at its native OTLP/HTTP endpoint. This
does not deploy a standalone OpenTelemetry Collector, Prometheus/Grafana or a
general metrics/log backend and dashboard. Those remain separate infrastructure
work; the local workload panel is not a replacement for them.

Complete service onboarding through the service's supported flows. Homarr board
setup and service accounts are separate from installing this utility. Keep local
passwords, API keys, session cookies, saved board responses and target identities
outside Git with owner-only permissions. A read-only public Homarr board is
viewable by anyone able to reach its existing loopback port; it grants no board
editing or management rights. It creates no public Internet endpoint.

For Langfuse v4, use [headless initialization](https://langfuse.com/self-hosting/administration/headless-initialization)
for an explicitly authorized isolated local owner/project while public signup
stays disabled. Test ingestion through
[`/api/public/otel/v1/traces`](https://langfuse.com/integrations/native/opentelemetry)
with `x-langfuse-ingestion-version: 4`; query `/api/public/v2/observations` to verify
persisted data. The old trace ingestion route rejects events in v4 `events_only`
mode. Constructed test spans must be labeled synthetic; do not enable a migration
compatibility mode or enroll real sources merely to make a test pass.

## Validation

Use `sh validation/run.sh lint` through the committed Docker entrypoint. It checks
the source and runs synthetic regressions for Conky geometry, small/secondary
monitors, missing pins, wrong cluster/namespace identities, duplicate ports,
unsafe bookmark URLs, weighted pane placement, native refresh scoping, health
envelope allowlisting, destination ownership and inactive/escaped hub links.
It does not launch a browser,
connect to a cluster, test authentication or enable the paused CI workflows.
