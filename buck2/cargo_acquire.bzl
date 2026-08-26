def _impl(ctx):
    out = ctx.actions.declare_output("source", dir = True)
    lock = ctx.actions.write_json("cargo-sources.json", ctx.attrs.spec)
    args = cmd_args(
        ctx.attrs.tool[RunInfo],
        "--spec", lock,
        "--output", out.as_output(),
    )
    ctx.actions.run(args, category = "cargo_acquire")
    return [DefaultInfo(default_output = out)]

cargo_acquire = rule(
    impl = _impl,
    attrs = {
        "spec": attrs.dict(key = attrs.string(), value = attrs.any()),
        "tool": attrs.exec_dep(providers = [RunInfo]),
    },
)
