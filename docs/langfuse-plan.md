# Langfuse setup

**Codex integration:** follow the [native/upstream comparison](codex-native-monitoring.md).
Native OTLP provides the initial operational-trace route. The upstream Langfuse
plugin is an optional richer, transcript-reading integration; no custom relay
or locally authored hook is planned.

Use the [operator setup guide](../application-infrastructure/README.md) for the
selected bundle, prerequisites, private inputs, validation and recovery.
The [telemetry contract](../application-infrastructure/runbooks/telemetry.md)
owns native diagnostics, plugin rich traces, importer history, content consent
and canonical-session cutover. No source is enabled by either document.

Earlier research is preserved in Git history; it is not a second installation path.

## Homarr shortcut

After the private Langfuse endpoint and Homarr board are separately approved and
available, add a native Homarr App shortcut:

- Name: `Langfuse`
- Destination: `https://<PRIVATE_LANGFUSE_ORIGIN>/` (placeholder only; replace
  in Homarr's private management UI after the HTTPS origin is verified)
- Description: `Langfuse dashboard`
- Status check: leave unset until server-side reachability and access behavior
  have been reviewed
- Board: add the App tile to the intended private board, or include it in a
  Bookmarks widget

Homarr Apps are saved shortcuts that can be displayed as App tiles or in the
Bookmarks widget; they do not create a Langfuse integration or grant Langfuse
access. Keep the board restricted using Homarr's existing access controls and
rely on Langfuse's own authentication. Do not commit the actual origin, API keys,
session material or other credentials. This entry is a plan only; the chart values
do not declare board content and no shortcut has been installed.

References: [Homarr Apps](https://homarr.dev/docs/management/apps/),
[Homarr Bookmarks](https://homarr.dev/docs/widgets/bookmarks/),
[Langfuse dashboards](https://langfuse.com/docs/metrics/features/custom-dashboards).
