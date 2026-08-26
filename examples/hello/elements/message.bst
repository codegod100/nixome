kind: manual

sources:
  - kind: local
    path: files

config:
  install-commands:
    - mkdir -p %{install-root}/share/hello
    - cp message.txt %{install-root}/share/hello/message.txt
