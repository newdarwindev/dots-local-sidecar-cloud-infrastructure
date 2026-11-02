# Public test-only TLS material

These files are copied from Node.js v24.11.0 test fixtures, with upstream license and SHA256 provenance. The private-key-labelled file is a **public, compromised-by-design test key**, not a user credential. Never mount it into a deployed service. Only isolated network-none loopback tests may use it. No key or certificate was generated.

New TLS overlay/tests are currently **unrun**: owner disabled GitHub workflows for budget and local Docker is absent.
