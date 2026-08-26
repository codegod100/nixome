# Generated source cell

This directory is a Buck2 cell containing fine-grained source acquisition
targets. The checked-in target is a bootstrap fixture for the pinned
`gnome-build-meta` repository.

Generate the complete cell from a source lock with:

```console
bst2nix generate-buck-sources source-lock.json -o generated/sources/BUCK
buck2 build generated_sources//:manifest
```

The generated `BUCK` file contains no credentials or local paths and is
deterministic for a given source lock.
