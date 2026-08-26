"""Buck2 execution platform backed by the official nixos/nix image."""

# Pin both the Nix release and image manifest. RE implementations commonly
# interpret this property directly; others match it against worker properties.
NIX_RBE_IMAGE = "docker://nixos/nix:2.35.2-amd64@sha256:617d914dba5384bf75adf17081583b69371031ec7defce36c34c5fa14fc819b0"

def _nix_rbe_platforms_impl(ctx):
    configuration = ConfigurationInfo(
        constraints = {},
        values = {},
    )
    platform = ExecutionPlatformInfo(
        label = ctx.label.raw_target(),
        configuration = configuration,
        executor_config = CommandExecutorConfig(
            local_enabled = False,
            remote_enabled = True,
            use_limited_hybrid = False,
            remote_execution_properties = {
                "OSFamily": "linux",
                "container-image": NIX_RBE_IMAGE,
            },
            remote_execution_use_case = "buck2-nix",
            remote_output_paths = "output_paths",
        ),
    )
    return [
        DefaultInfo(),
        ExecutionPlatformRegistrationInfo(platforms = [platform]),
    ]

nix_rbe_platforms = rule(
    impl = _nix_rbe_platforms_impl,
    attrs = {},
)
