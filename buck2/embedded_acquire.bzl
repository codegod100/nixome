def _impl(ctx):
    out = ctx.actions.declare_output("source", dir = True)
    args = cmd_args(
        ctx.attrs.tool[RunInfo],
        "--encoding", ctx.attrs.encoding,
        "--data", ctx.attrs.data,
        "--filename", ctx.attrs.filename,
        "--output", out.as_output(),
    )
    ctx.actions.run(args, category = "embedded_acquire")
    return [DefaultInfo(default_output = out)]

embedded_acquire = rule(
    impl = _impl,
    attrs = {
        "encoding": attrs.enum(["base64"]),
        "data": attrs.string(),
        "filename": attrs.string(),
        "tool": attrs.exec_dep(providers = [RunInfo]),
    },
)
