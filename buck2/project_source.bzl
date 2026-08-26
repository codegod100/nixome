def _impl(ctx):
    out = ctx.actions.declare_output("source", dir = True)
    args = cmd_args(
        ctx.attrs.tool[RunInfo],
        "--url", ctx.attrs.url,
        "--revision", ctx.attrs.revision,
        "--path", ctx.attrs.path,
        "--output", out.as_output(),
    )
    ctx.actions.run(args, category = "project_source")
    return [DefaultInfo(default_output = out)]

project_source = rule(
    impl = _impl,
    attrs = {
        "url": attrs.string(),
        "revision": attrs.string(),
        "path": attrs.string(),
        "tool": attrs.exec_dep(providers = [RunInfo]),
    },
)
