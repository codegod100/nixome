def _python_tool_impl(ctx):
    args = cmd_args(
        "nix", "--extra-experimental-features", "nix-command flakes",
        "shell", "nixpkgs#python3", "--command", "python3", ctx.attrs.src,
    )
    args.hidden(ctx.attrs.srcs)
    return [
        DefaultInfo(),
        RunInfo(args = args),
    ]

python_tool = rule(
    impl = _python_tool_impl,
    attrs = {
        "src": attrs.source(),
        "srcs": attrs.list(attrs.source(), default = []),
    },
)
