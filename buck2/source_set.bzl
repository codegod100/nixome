def _impl(ctx):
    return [DefaultInfo(default_outputs = ctx.attrs.srcs)]

source_set = rule(
    impl = _impl,
    attrs = {"srcs": attrs.list(attrs.source())},
)
