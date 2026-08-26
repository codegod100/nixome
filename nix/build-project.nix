{ pkgs, graph, projectRoot }:

assert graph.formatVersion == 1;

let
  lib = pkgs.lib;

  buildElement = name:
    let
      element = graph.elements.${name};
      buildDependencies = map buildElement element.buildDependencies;
      runDependencies = map buildElement element.runDependencies;
      allDependencies = lib.unique (buildDependencies ++ runDependencies);

      sourceCommands = lib.concatMapStringsSep "\n" (source: ''
        mkdir -p "$buildRoot/${lib.escapeShellArg source.directory}"
        cp -R ${projectRoot + "/${source.path}"}/. \
          "$buildRoot/${lib.escapeShellArg source.directory}/"
      '') element.sources;

      variableNames = map (name: "%{${name}}") (builtins.attrNames element.variables);
      variableValues = builtins.attrValues element.variables;
      commandScript = lib.replaceStrings variableNames variableValues
        (lib.concatStringsSep "\n" element.commands);
    in
    pkgs.runCommand
      "bst2nix-${lib.replaceStrings [ "/" ".bst" ] [ "-" "" ] name}"
      {
        nativeBuildInputs = [ pkgs.bash pkgs.coreutils pkgs.gnutar ];
        passthru = {
          inherit name;
          bst2nixGraph = graph;
        };
      }
      ''
        set -euo pipefail
        buildRoot="$NIX_BUILD_TOP/build"
        sysroot="$NIX_BUILD_TOP/sysroot"
        installRoot="$out"
        mkdir -p "$buildRoot" "$sysroot" "$installRoot"

        ${lib.concatMapStringsSep "\n" (dependency: ''
          cp -RT --no-preserve=mode ${dependency} "$sysroot"
        '') allDependencies}

        ${sourceCommands}

        substituteCommand() {
          local command="$1"
          command="''${command//\%\{build-root\}/$buildRoot}"
          command="''${command//\%\{install-root\}/$installRoot}"
          command="''${command//\%\{sysroot\}/$sysroot}"
          if [[ "$command" =~ %\{[^}]+\} ]]; then
            echo "bst2nix: unresolved variable in: $command" >&2
            exit 1
          fi
          printf '%s\n' "$command"
        }

        cd "$buildRoot"
        while IFS= read -r command; do
          [[ -z "$command" ]] && continue
          ${pkgs.bash}/bin/bash -euo pipefail -c "$(substituteCommand "$command")"
        done <<'BST2NIX_COMMANDS'
        ${commandScript}
        BST2NIX_COMMANDS

        ${lib.concatMapStringsSep "\n" (dependency: ''
          cp -RT --no-preserve=mode ${dependency} "$installRoot"
        '') runDependencies}
      '';
in
buildElement graph.target
