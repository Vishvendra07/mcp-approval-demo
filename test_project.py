import sqlite3
import sys
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from project import approve, propose, read_item, ready


class ApprovalTests(unittest.IsolatedAsyncioTestCase):
    def test_exact_payload_and_stale_proposal(self):
        with sqlite3.connect(":memory:") as db:
            ready(db)
            a, b = (propose(db, "KIT-100", quantity) for quantity in (8, 9))
            with self.assertRaises(ValueError):
                approve(db, a["proposal_id"], b["digest"])
            self.assertEqual(read_item(db, "KIT-100")["quantity"], 5)
            self.assertEqual(approve(db, a["proposal_id"], a["digest"])["state"], "applied")
            self.assertTrue(approve(db, a["proposal_id"], a["digest"])["replayed"])
            self.assertEqual(approve(db, b["proposal_id"], b["digest"])["state"], "stale")

    async def test_real_stdio_client_can_propose_but_catalog_is_unchanged(self):
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "catalog.sqlite"
            command = StdioServerParameters(
                command=sys.executable,
                args=[
                    str(Path(__file__).with_name("project.py")),
                    "serve",
                    "--database",
                    str(db_path),
                ],
            )
            async with stdio_client(command) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    self.assertEqual(
                        {tool.name for tool in (await client.list_tools()).tools},
                        {"read_catalog_item", "propose_quantity"},
                    )
                    reply = await client.call_tool(
                        "propose_quantity", {"sku": "KIT-100", "quantity": 10}
                    )
                    self.assertFalse(reply.isError)
            with closing(sqlite3.connect(db_path)) as db:
                self.assertEqual(read_item(db, "KIT-100")["quantity"], 5)
                self.assertEqual(db.execute("SELECT state FROM proposals").fetchone(), ("pending",))
