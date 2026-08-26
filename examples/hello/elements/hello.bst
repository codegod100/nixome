kind: manual

depends:
  - filename: message.bst
    type: run

config:
  install-commands:
    - mkdir -p %{install-root}/bin
    - printf '#!/bin/sh\ncat "$(dirname "$0")/../share/hello/message.txt"\n' > %{install-root}/bin/hello
    - chmod +x %{install-root}/bin/hello
