"""A small Nix build rule intended for a Nix-capable RE execution platform."""

def _nix_build_impl(ctx):
    # Nix canonicalizes flake inputs and follows symlinks. A symlinked_dir can
    # therefore become a self-referential tree in an RE input root; materialize
    # a copied directory instead.
    project = ctx.actions.copied_dir(
        "project",
        {
            src.short_path: src
            for src in ctx.attrs.srcs
        },
    )
    output = ctx.actions.declare_output("result", dir = True)

    script = cmd_args(
        "set -euo pipefail\n",
        "export HOME=\"$PWD/.nix-home\"\n",
        "export XDG_CACHE_HOME=\"$HOME/.cache\"\n",
        "mkdir -p \"$XDG_CACHE_HOME\" \"$HOME\"\n",
        "output_path=\"$PWD/",
        output.as_output(),
        "\"\n",
        "cd ",
        project,
        "\n",
        "store_path=$(nix --extra-experimental-features 'nix-command flakes' ",
        "build --no-link --no-write-lock-file --print-out-paths ",
        ctx.attrs.flake,
        ")\n",
        "test \"$(printf '%s\\n' \"$store_path\" | wc -l)\" -eq 1 || ",
        "{ echo 'nix_build requires exactly one output path' >&2; exit 1; }\n",
        "mkdir -p \"$output_path\"\n",
        # Dereference the store path. Buck's CAS must receive actual files, not
        # a symlink into the ephemeral worker's /nix/store.
        "cp -aL \"$store_path\"/. \"$output_path\"/\n",
        delimiter = "",
    )

    ctx.actions.run(
        cmd_args("/bin/sh", "-c", script),
        category = "nix_build",
        identifier = ctx.label.name,
        env = {
            "NIX_CONFIG": "sandbox = false\naccept-flake-config = false",
        },
    )

    return [DefaultInfo(default_output = output)]

nix_build = rule(
    impl = _nix_build_impl,
    attrs = {
        "flake": attrs.string(),
        "srcs": attrs.list(attrs.source(), default = []),
    },
)
