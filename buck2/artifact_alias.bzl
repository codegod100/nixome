def _impl(ctx):
    outputs = ctx.attrs.actual[DefaultInfo].default_outputs
    return [DefaultInfo(default_outputs = outputs)]

artifact_alias = rule(
    impl = _impl,
    attrs = {
        "actual": attrs.dep(providers = [DefaultInfo]),
    },
)
