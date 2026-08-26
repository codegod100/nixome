def _impl(ctx):
    out = ctx.actions.declare_output("artifact", dir = True)
    spec = ctx.actions.write_json("element-spec.json", ctx.attrs.spec)
    args = cmd_args(ctx.attrs.tool[RunInfo], "--spec", spec, "--output", out.as_output())
    for source_id, dependency in sorted(ctx.attrs.sources.items()):
        outputs = dependency[DefaultInfo].default_outputs
        if len(outputs) != 1:
            fail("source group must have exactly one output")
        args.add("--source", source_id, outputs[0])
    for name, dependency in sorted(ctx.attrs.dependencies.items()):
        outputs = dependency[DefaultInfo].default_outputs
        if len(outputs) != 1:
            fail("element dependency must have exactly one output")
        args.add("--dependency", name, outputs[0])
    ctx.actions.run(args, category = "element_execute")
    return [DefaultInfo(default_output = out)]

element_execute = rule(
    impl = _impl,
    attrs = {
        "spec": attrs.dict(key = attrs.string(), value = attrs.any()),
        "sources": attrs.dict(
            key = attrs.string(),
            value = attrs.dep(providers = [DefaultInfo]),
        ),
        "dependencies": attrs.dict(
            key = attrs.string(),
            value = attrs.dep(providers = [DefaultInfo]),
        ),
        "tool": attrs.exec_dep(providers = [RunInfo]),
    },
)
