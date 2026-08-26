def _impl(ctx):
    out = ctx.actions.declare_output("source", dir = True)
    args = cmd_args(
        ctx.attrs.tool[RunInfo],
        "--url", ctx.attrs.url,
        "--sha256", ctx.attrs.sha256,
        "--kind", ctx.attrs.kind,
        "--output", out.as_output(),
    )
    if ctx.attrs.filename:
        args.add("--filename", ctx.attrs.filename)
    ctx.actions.run(args, category = "http_acquire")
    return [DefaultInfo(default_output = out)]

http_acquire = rule(
    impl = _impl,
    attrs = {
        "url": attrs.string(),
        "sha256": attrs.string(),
        "kind": attrs.enum(["tar", "zip", "remote", "archive"]),
        "filename": attrs.option(attrs.string(), default = None),
        "tool": attrs.exec_dep(providers = [RunInfo]),
    },
)
