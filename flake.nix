{
  description = "Translate a small BuildStream subset into native Nix builds";

  # Keep remote builds reproducible even before a generated flake.lock exists.
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/56c02bc00adcf003215cc4bd996d6efaf4cff188";
  inputs.gnome-build-meta = {
    url = "git+https://gitlab.gnome.org/GNOME/gnome-build-meta.git?rev=cf996738158c1a3291a8c98df88892b26d335bc2";
    flake = false;
  };
  inputs.freedesktop-sdk = {
    url = "git+https://gitlab.com/freedesktop-sdk/freedesktop-sdk.git?rev=e076d4978ee6945763486f6ebd755d189460e4e7";
    flake = false;
  };

  outputs = { self, nixpkgs, gnome-build-meta, freedesktop-sdk }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in {
      packages = forAllSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          bst2nix = pkgs.python3Packages.buildPythonApplication {
            pname = "bst2nix";
            version = "0.1.0";
            pyproject = true;
            src = self;
            build-system = [ pkgs.python3Packages.setuptools ];
            dependencies = [ pkgs.python3Packages.pyyaml ];
            nativeCheckInputs = [ pkgs.python3Packages.pytestCheckHook ];
          };
          exampleGraph = builtins.fromJSON (builtins.readFile ./examples/hello/graph.json);
          gnomeosAudit = pkgs.runCommand "bst2nix-gnomeos-audit" {
            nativeBuildInputs = [ bst2nix ];
          } ''
            mkdir -p "$out"
            bst2nix audit \
              ${gnome-build-meta} \
              oci/gnomeos/image.bst \
              -o "$out/audit.json"
          '';
          gnomeosGraphLock = pkgs.runCommand "bst2nix-gnomeos-graph-lock" {
            nativeBuildInputs = [ bst2nix ];
          } ''
            mkdir -p "$out"
            bst2nix lock-graph \
              --options ${./examples/gnomeos/options.json} \
              --revision gnome=cf996738158c1a3291a8c98df88892b26d335bc2 \
              --revision freedesktop-sdk=e076d4978ee6945763486f6ebd755d189460e4e7 \
              --junction freedesktop-sdk.bst=${freedesktop-sdk} \
              --junction-options \
                freedesktop-sdk.bst=${./examples/gnomeos/freedesktop-sdk-options.json} \
              ${gnome-build-meta} \
              oci/gnomeos/image.bst \
              -o "$out/graph-lock.json"
          '';
          gnomeosSourceLock = pkgs.runCommand "bst2nix-gnomeos-source-lock" {
            nativeBuildInputs = [ bst2nix ];
          } ''
            mkdir -p "$out"
            bst2nix lock-sources \
              ${gnomeosGraphLock}/graph-lock.json \
              --aliases gnome=${gnome-build-meta}/include/aliases.yml \
              --aliases \
                freedesktop-sdk=${freedesktop-sdk}/include/_private/aliases.yml \
              -o "$out/source-lock.json"
          '';
        in {
          inherit bst2nix;
          gnomeos-audit = gnomeosAudit;
          gnomeos-graph-lock = gnomeosGraphLock;
          gnomeos-source-lock = gnomeosSourceLock;
          default = bst2nix;
          example = import ./nix/build-project.nix {
            inherit pkgs;
            graph = exampleGraph;
            projectRoot = ./examples/hello;
          };
        });

      apps = forAllSystems (system: {
        bst2nix = {
          type = "app";
          program = "${self.packages.${system}.bst2nix}/bin/bst2nix";
        };
        default = self.apps.${system}.bst2nix;
        gnomeos-audit = {
          type = "app";
          program = "${nixpkgs.legacyPackages.${system}.writeShellApplication {
            name = "bst2nix-gnomeos-audit";
            runtimeInputs = [ self.packages.${system}.bst2nix ];
            text = ''
              exec bst2nix audit \
                ${gnome-build-meta} \
                oci/gnomeos/image.bst "$@"
            '';
          }}/bin/bst2nix-gnomeos-audit";
        };
      });

      checks = forAllSystems (system: {
        inherit (self.packages.${system})
          bst2nix example gnomeos-audit gnomeos-graph-lock;
          inherit (self.packages.${system}) gnomeos-source-lock;
      });

      devShells = forAllSystems (system:
        let pkgs = nixpkgs.legacyPackages.${system};
        in {
          default = pkgs.mkShell {
            packages = [
              self.packages.${system}.bst2nix
              pkgs.python3Packages.pytest
            ];
          };
        });
    };
}
