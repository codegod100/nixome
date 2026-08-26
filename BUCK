load("//buck2:git_acquire.bzl", "git_acquire")
load("//buck2:nix_build.bzl", "nix_build")

PROJECT_SRCS = glob(
    ["**"],
    exclude = [
        ".git/**",
        "buck-out/**",
        "result",
        "result-*",
    ],
)

git_acquire(
    name = "acquire-gnome-build-meta",
    revision = "cf996738158c1a3291a8c98df88892b26d335bc2",
    tool = "//tools:acquire_git",
    url = "https://gitlab.gnome.org/GNOME/gnome-build-meta.git",
)

nix_build(
    name = "example",
    flake = ".#example",
    srcs = PROJECT_SRCS,
)

nix_build(
    name = "gnomeos-audit",
    flake = ".#gnomeos-audit",
    srcs = PROJECT_SRCS,
)

nix_build(
    name = "gnomeos-graph-lock",
    flake = ".#gnomeos-graph-lock",
    srcs = PROJECT_SRCS,
)

nix_build(
    name = "gnomeos-source-lock",
    flake = ".#gnomeos-source-lock",
    srcs = PROJECT_SRCS,
)
