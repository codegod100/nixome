# bst2nix

`bst2nix` is an experimental translator from a small subset of
[BuildStream](https://buildstream.build/) projects to native Nix derivations.
BuildStream is not used at evaluation or build time.

The proof of concept supports:

- `project.conf` variables
- `manual` elements
- `local` sources
- build and runtime dependencies
- `%{variable}` expansion
- `configure-commands`, `build-commands`, `install-commands`, and
  `strip-commands`
- composing dependency artifacts into each element's `/`

It intentionally rejects unknown element and source kinds rather than silently
producing a different build.

## Try the example

```console
$ nix run .#bst2nix -- lock examples/hello hello.bst -o examples/hello/graph.json
$ nix build .#example
$ ./result/bin/hello
hello from bst2nix
```

The generated `graph.json` is an inspectable, deterministic intermediate
representation. `nix/build-project.nix` turns that graph into one derivation per
element.

Run the translator tests with:

```console
$ nix flake check
```

## Build through Buck2 remote execution

The root `//:example` target runs `nix build .#example` on a remote worker
selected through Buck2's REAPI support:

```console
$ export BUILDBUDDY_API_KEY=...
$ buck2 build //:example
$ buck2 build //:example --show-output
```

The execution platform uses the official `nixos/nix:2.35.2-amd64` Linux image
pinned by its manifest digest. Local execution is disabled so a missing or
misconfigured remote executor fails rather than silently building on the
developer machine.

The checked-in endpoint is BuildBuddy Cloud. `.buckconfig.local.example`
provides an override template for BuildBarn or another REAPI service.

The RE service must support the `container-image` platform property, or provide
a worker registered with the matching property. The worker needs:

- a writable `/nix` store
- outbound access to fetch flake inputs, unless they are already cached
- enough disk for the Nix closure

The rule dereferences the realized store output into Buck2's declared output
directory. Consequently, the RE content-addressed store receives the files
rather than a symlink pointing into an ephemeral worker's `/nix/store`.

## Current semantics

Sources are copied below `%{build-root}`. Commands run in that directory with
`%{install-root}` pointing at a fresh output tree. Dependency outputs are merged
into `%{sysroot}` before commands run. Runtime dependencies are also propagated
to the final artifact.

This is sufficient to validate the architecture, but it is not yet compatible
with GNOME OS. The next useful additions are `git` and `tar` source locking,
followed by `meson`, `autotools`, `compose`, `filter`, and junction support.

## Non-goals of the proof of concept

- Parsing arbitrary BuildStream plugins
- Reproducing BuildStream cache keys
- Supporting junctions or conditional YAML
- Building an entire `gnome-build-meta` checkout

See [docs/design.md](docs/design.md) for the boundary between translation and
building.
