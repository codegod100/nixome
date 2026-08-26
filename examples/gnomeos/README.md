# GNOME OS compatibility fixture

This example audits the real upstream GNOME OS OCI image target:

```text
oci/gnomeos/image.bst
```

The source is `GNOME/gnome-build-meta`, pinned in the root flake to revision
`cf996738158c1a3291a8c98df88892b26d335bc2`. No BuildStream executable is used.
The target options are pinned in `options.json`; the architecture is
`x86_64`, matching the Buck2 remote execution worker.

Run:

```console
$ nix run .#gnomeos-audit
```

The command emits JSON containing:

- every same-project element reachable from the OCI target
- BuildStream element and source kinds used by that closure
- dependencies crossing the `freedesktop-sdk.bst` junction
- the kinds not yet implemented by `bst2nix`

To save an updated report:

```console
$ nix run .#gnomeos-audit -- -o examples/gnomeos/audit.json
```

Build the report as a native Nix derivation, locally or through the configured
Buck2 remote executor:

```console
$ nix build .#gnomeos-audit
$ buck2 build //:gnomeos-audit --show-output
```

Generate the fully qualified GNOME and freedesktop-sdk dependency lock:

```console
$ nix build .#gnomeos-graph-lock
$ buck2 build //:gnomeos-graph-lock --show-output
```

The result contains `graph-lock.json`, with immutable project revisions,
resolved GNOME overrides, dependency scopes, composed element configuration,
and qualified edges for the complete `x86_64` closure.

Normalize, validate, and deduplicate every source declaration:

```console
$ nix build .#gnomeos-source-lock
$ buck2 build //:gnomeos-source-lock --show-output
```

The resulting `source-lock.json` resolves project URL aliases, extracts commits
from Git-describe refs, validates existing SHA-256 content refs, validates local
paths, and assigns each unique normalized source a stable content-derived ID.

An audit is deliberately not called a lock or build. Junction resolution,
project includes, options, conditional YAML, and several plugin kinds must be
implemented before `bst2nix` can produce the GNOME OS derivation graph.
