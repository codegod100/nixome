def _impl(ctx):
    out = ctx.actions.declare_output("source", dir = True)
    args = cmd_args(
        ctx.attrs.tool[RunInfo],
        "--url", ctx.attrs.url,
        "--digest", ctx.attrs.digest,
        "--architecture", ctx.attrs.architecture,
        "--output", out.as_output(),
    )
    ctx.actions.run(args, category = "oci_acquire")
    return [DefaultInfo(default_output = out)]

oci_acquire = rule(
    impl = _impl,
    attrs = {
        "url": attrs.string(),
        "digest": attrs.string(),
        "architecture": attrs.string(),
        "tool": attrs.exec_dep(providers = [RunInfo]),
    },
)
