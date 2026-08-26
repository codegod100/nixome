# Generated GNOME OS element cell

This Buck2 cell holds the native element DAG translated from the pinned GNOME
OS BuildStream graph. Generate it together with the corresponding source cell:

```console
tools/generate_gnomeos_cells.sh
```

Then build the top-level OCI target:

```console
buck2 build //:gnomeos-oci --show-output
```

The generated `BUCK` file is deterministic for the graph and source locks and
contains a public `target` alias for `gnome:oci/gnomeos/image.bst`.
