def _python_tool_impl(ctx):
    args = cmd_args(
        "nix", "--extra-experimental-features", "nix-command flakes",
        "shell", "nixpkgs#python3", "nixpkgs#openssl", "nixpkgs#gnupg",
        "nixpkgs#bubblewrap", "nixpkgs#proot", "nixpkgs#patch", "--command",
        "env", "PYTHONPATH=.", "python3", ctx.attrs.src,
    )
    for dependency in ctx.attrs.srcs:
        args.add(cmd_args(hidden = dependency[DefaultInfo].default_outputs))
    return [
        DefaultInfo(),
        RunInfo(args = args),
    ]

python_tool = rule(
    impl = _python_tool_impl,
    attrs = {
        "src": attrs.source(),
        "srcs": attrs.list(attrs.dep(providers = [DefaultInfo]), default = []),
    },
)
