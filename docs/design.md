# Design

The translator and builder are separate by design:

1. `bst2nix lock` parses BuildStream YAML, validates the supported subset, walks
   dependencies, and emits canonical JSON.
2. `nix/build-project.nix` recursively converts that JSON into Nix
   derivations.
3. Each derivation stages dependency artifacts, copies declared sources, runs
   commands, and captures an immutable filesystem artifact.

This split keeps YAML parsing and future source-ref resolution out of Nix
evaluation while leaving all actual compilation and composition to Nix.

## Compatibility rule

Unsupported syntax is an error. It must never be ignored because a successful
but semantically different OS image is worse than an early failure.

## Reproducibility

The current `local` source is already a Nix input because `projectRoot` is a
store path. Future remote source support must resolve mutable references in the
lock command and represent each result with a Nix-compatible content hash.

## Filesystem model

BuildStream artifacts are filesystem trees, unlike conventional Nix packages
whose dependencies remain at distinct store paths. The generic builder
therefore stages dependency outputs into a synthetic sysroot. This model can
later be moved into a sandbox helper when builds need absolute `/usr` paths.
