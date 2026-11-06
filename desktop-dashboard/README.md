# Desktop dashboards beside Conky

An optional Linux/X11 login-session launcher for the minimal WebKit/GTK browser
[surf](https://surf.suckless.org/). It creates a borderless desktop-type window,
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

Edit the private JSON before starting. `links` contains `id`, `name`, optional
`description` and either a credential-free HTTPS `url`, an authorized `forward`
ID with relative `path`, or an inactive `status`. `start` selects a link ID or
`home`. The generated home page lists connection status and bookmarks without
running staged services. Do not put passwords, tokens or credential-bearing URLs
in this configuration, the repository or process arguments.

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
`desktop-dashboard --home` do the same. Surf's **Ctrl+h** goes back and **Ctrl+r**
reloads. Configure Homarr App links to open in the same window; popup-created
browser windows are ordinary drill-down windows, outside this supervisor's layout.

`desktop-dashboard --status` reports the last observed connection sample and time
and checks the supervisor lock. It alone does not prove browser or UI health.
`desktop-dashboard --stop` stops
the owned browser and forwards. Disable later login startup by setting
`Hidden=true` in `~/.config/autostart/desktop-dashboard.desktop`, then stop it.
Re-enable by removing that line. No reboot is needed.

State is under `~/.local/state/desktop-dashboard/`: append-only launcher/forward
logs and generated `status.json`. The generated hub and private cookie database
are under `~/.surf/desktop-dashboard/`, within surf's distribution AppArmor
allowlist; no AppArmor relaxation is required. State files use owner-only
permissions and are never source artifacts. Browser cookies can confer access;
preserve their privacy. The runtime control socket and
lock use `$XDG_RUNTIME_DIR/desktop-dashboard` when available. A restart preserves
existing logs and cookies. Uninstallation may remove the launcher and two desktop
entries, but must preserve any histories, service data, credentials and receipts.

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
unsafe bookmark URLs and inactive/escaped hub links. It does not launch a browser,
connect to a cluster, test authentication or enable the paused CI workflows.
