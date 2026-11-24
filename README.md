# MCP Approval Demo

The MCP client reads and proposes a catalog change. A separate operator command applies the exact reviewed action and writes a receipt.

[Source](project.py) · [Demo evidence](evidence/demo.json) · [Verification](evidence/checks.json)

## Run locally

Requires Python 3.11+.

```sh
python -m pip install -r requirements.txt
python project.py
python -m unittest discover -v
```

## Engineering decision

Keep proposal and approval entry points separate, and bind approval to the payload hash and record revision.

Local SQLite, stdio MCP, and synthetic inventory. Protect the sandbox file with OS access controls in any shared environment.

Start the MCP tool server with `python project.py serve --database catalog.sqlite`. The explicit approval command takes `--proposal`, `--digest`, and the same database.

[Technology or project reference](https://github.com/modelcontextprotocol/python-sdk)
