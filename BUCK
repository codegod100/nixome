load("//buck2:nix_build.bzl", "nix_build")

nix_build(
    name = "example",
    flake = ".#example",
    srcs = glob(
        ["**"],
        exclude = [
            ".git/**",
            "buck-out/**",
            "result",
            "result-*",
        ],
    ),
)
