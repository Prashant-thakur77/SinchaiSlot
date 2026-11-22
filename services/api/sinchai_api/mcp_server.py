"""sinchaislot-mcp: the platform's typed tools as an MCP server (stdio).

Any MCP client can operate the platform in a demo, e.g.:
    {"command": "uv", "args": ["run", "sinchaislot-mcp"], "cwd": "<repo>"}

Tools that spend money, water or energy are exposed with a required `confirmed` flag: without
`confirmed: true` they return a read-back for the human to approve instead of running.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from . import db, state, tools

mcp = FastMCP("sinchaislot")


def _register(t: tools.Tool) -> None:
    def run(args: dict | None = None, confirmed: bool = False) -> str:
        args = args or {}
        if t.confirm and not confirmed:
            return json.dumps({"needs_confirmation": True, "tool": t.name, "args": args,
                               "message": "Read this back to the farmer or Saur Mitra; call again with confirmed=true."})
        res, ms, err = tools.timed_call(t.name, args, tools.ToolContext(role="operator", channel="mcp"))
        return json.dumps(res, default=str)

    schema = json.dumps(t.schema())
    run.__name__ = t.name
    run.__doc__ = f"{t.description}\n\nargs JSON schema: {schema}" + ("\nRequires confirmed=true to execute." if t.confirm else "")
    mcp.tool(name=t.name, description=run.__doc__)(run)


for _t in tools.REGISTRY.values():
    _register(_t)


@mcp.resource("sinchaislot://proof")
def proof_resource() -> str:
    return json.dumps(state.load_proof()["headline"], indent=2)


@mcp.resource("sinchaislot://plan")
def plan_resource() -> str:
    return json.dumps(state.get_state().snapshot(), default=str)


def main() -> None:
    db.init_db()
    mcp.run()


if __name__ == "__main__":
    main()
