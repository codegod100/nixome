def _impl(ctx):
    out = ctx.actions.declare_output("materialized-source-manifest.json")
    args = cmd_args(ctx.attrs.tool[RunInfo], "--output", out.as_output())
    for source_id, dependency in sorted(ctx.attrs.sources.items()):
        outputs = dependency[DefaultInfo].default_outputs
        if len(outputs) != 1:
            fail("source {} must have exactly one output".format(source_id))
        args.add("--source", source_id, outputs[0])
    for dependency in ctx.attrs.groups:
        outputs = dependency[DefaultInfo].default_outputs
        if len(outputs) != 1:
            fail("source group must have exactly one output")
        args.add("--group", outputs[0])
    ctx.actions.run(args, category = "source_manifest")
    return [DefaultInfo(default_output = out)]

source_manifest = rule(
    impl = _impl,
    attrs = {
        "sources": attrs.dict(
            key = attrs.string(),
            value = attrs.dep(providers = [DefaultInfo]),
            default = {},
        ),
        "groups": attrs.list(attrs.dep(providers = [DefaultInfo]), default = []),
        "tool": attrs.exec_dep(providers = [RunInfo]),
    },
)
