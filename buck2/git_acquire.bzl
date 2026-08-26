def _impl(ctx):
    out=ctx.actions.declare_output("source",dir=True)
    args=cmd_args(ctx.attrs.tool[RunInfo],"--url",ctx.attrs.url,"--revision",ctx.attrs.revision,"--output",out.as_output())
    if ctx.attrs.submodules: args.add("--submodules")
    ctx.actions.run(args,category="git_acquire",local_only=False)
    return [DefaultInfo(default_output=out)]

git_acquire=rule(impl=_impl,attrs={
    "url":attrs.string(),
    "revision":attrs.string(),
    "submodules":attrs.bool(default=False),
    "tool":attrs.exec_dep(providers=[RunInfo]),
})

def _repo_impl(ctx):
    out = ctx.actions.declare_output("sources", dir = True)
    args = cmd_args(ctx.attrs.tool[RunInfo], "--url", ctx.attrs.url, "--output", out.as_output())
    for source_id, revision in sorted(ctx.attrs.sources.items()):
        args.add("--source", "{}={}".format(source_id, revision))
    if ctx.attrs.submodules:
        args.add("--submodules")
    ctx.actions.run(args, category = "git_repo_acquire", local_only = False)
    return [DefaultInfo(default_output = out)]

git_repo_acquire = rule(
    impl = _repo_impl,
    attrs = {
        "url": attrs.string(),
        "sources": attrs.dict(key = attrs.string(), value = attrs.string()),
        "submodules": attrs.bool(default = False),
        "tool": attrs.exec_dep(providers = [RunInfo]),
    },
)
