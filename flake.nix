{
  description = "Translate a small BuildStream subset into native Nix builds";

  # Keep remote builds reproducible even before a generated flake.lock exists.
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/56c02bc00adcf003215cc4bd996d6efaf4cff188";

  outputs = { self, nixpkgs }:
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
        in {
          inherit bst2nix;
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
      });

      checks = forAllSystems (system: {
        inherit (self.packages.${system}) bst2nix example;
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
