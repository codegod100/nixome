def _python_tool_impl(ctx):
    return [
        DefaultInfo(),
        RunInfo(args = cmd_args(
            "nix", "--extra-experimental-features", "nix-command flakes",
            "shell", "nixpkgs#python3", "--command", "python3", ctx.attrs.src,
        )),
    ]

python_tool = rule(
    impl = _python_tool_impl,
    attrs = {"src": attrs.source()},
)
