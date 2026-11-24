"""Expose catalog reads and proposals through MCP, then approve locally by digest."""

import argparse
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4


def ready(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS catalog (sku TEXT PRIMARY KEY, quantity INTEGER NOT NULL, version INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL);
        INSERT OR IGNORE INTO catalog VALUES ('KIT-100',5,1);
    """)


def read_item(db, sku):
    row = db.execute("SELECT quantity,version FROM catalog WHERE sku=?", (sku,)).fetchone()
    return {"sku": sku, "quantity": row[0], "version": row[1]} if row else None


def propose(db, sku, quantity):
    if type(quantity) is not int or not 0 <= quantity <= 100:
        raise ValueError("Demo quantity must be an integer from 0 through 100")
    current = read_item(db, sku)
    if current is None:
        raise ValueError("Unknown SKU")
    payload = {"sku": sku, "quantity": quantity, "expected_version": current["version"]}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    proposal_id = uuid4().hex
    with db:
        db.execute(
            "INSERT INTO proposals VALUES (?,?,?,?)", (proposal_id, canonical, digest, "pending")
        )
    return {"proposal_id": proposal_id, "payload": payload, "digest": digest, "state": "pending"}


def approve(db, proposal_id, digest):
    with db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT payload,digest,state FROM proposals WHERE id=?", (proposal_id,)
        ).fetchone()
        if row is None or row[1] != digest:
            raise ValueError("Proposal and exact payload hash are required")
        if row[2] != "pending":
            return {"proposal_id": proposal_id, "state": row[2], "replayed": True}
        payload = json.loads(row[0])
        changed = db.execute(
            "UPDATE catalog SET quantity=?,version=version+1 WHERE sku=? AND version=?",
            (payload["quantity"], payload["sku"], payload["expected_version"]),
        ).rowcount
        state = "applied" if changed else "stale"
        db.execute("UPDATE proposals SET state=? WHERE id=?", (state, proposal_id))
        return {"proposal_id": proposal_id, "state": state, "replayed": False}


def serve(path):
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("Synthetic catalog")
    with closing(sqlite3.connect(path)) as db:
        ready(db)

    @server.tool()
    def read_catalog_item(sku: str) -> dict:
        """Read a synthetic catalog entry and its current version."""
        with closing(sqlite3.connect(path)) as db:
            return read_item(db, sku) or {"error": "unknown SKU"}

    @server.tool()
    def propose_quantity(sku: str, quantity: int) -> dict:
        """Create a pending proposal. The catalog changes only after local review."""
        with closing(sqlite3.connect(path)) as db:
            return propose(db, sku, quantity)

    server.run(transport="stdio")


def demo():
    with (
        TemporaryDirectory() as directory,
        closing(sqlite3.connect(Path(directory) / "catalog.sqlite")) as db,
    ):
        ready(db)
        suggestion = propose(db, "KIT-100", 8)
        before = read_item(db, "KIT-100")
        result = approve(db, suggestion["proposal_id"], suggestion["digest"])
        return {
            "before": before,
            "proposal": suggestion,
            "receipt": result,
            "after": read_item(db, "KIT-100"),
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["demo", "serve", "approve"], default="demo", nargs="?")
    parser.add_argument(
        "--database", type=Path, default=Path(os.environ.get("CATALOG_DB", "catalog.sqlite"))
    )
    parser.add_argument("--proposal")
    parser.add_argument("--digest")
    args = parser.parse_args()
    if args.command == "serve":
        serve(args.database)
    elif args.command == "demo":
        print(json.dumps(demo(), indent=2))
    else:
        if not args.proposal or not args.digest:
            parser.error("Provide --proposal and --digest from the reviewed payload")
        with closing(sqlite3.connect(args.database)) as db:
            ready(db)
            print(json.dumps(approve(db, args.proposal, args.digest), indent=2))
