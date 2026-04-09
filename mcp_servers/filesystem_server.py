"""MCP Filesystem — sandbox en WORKSPACE_PATH"""
import asyncio, os, sys
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ── Logger ───────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
from logger import get_logger
log = get_logger("filesystem")

# ── Servidor ─────────────────────────────────────────────────────────────────
WS = Path(os.environ.get("WORKSPACE_PATH", "/tmp/ws"))
WS.mkdir(parents=True, exist_ok=True)
server = Server("fs")

log.info("servidor iniciado", workspace=str(WS))


def safe(p: str) -> Path:
    ws = WS.resolve()
    full = (ws / p.lstrip("/").lstrip("./")).resolve()
    if not str(full).startswith(str(ws)):
        log.warning("path traversal bloqueado", attempted_path=p, workspace=str(ws))
        raise ValueError("fuera de sandbox")
    return full


@server.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="write_file",
            description="Escribe archivo",
            inputSchema={
                "type": "object",
                "properties": {
                    "path":    {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        ),
        types.Tool(
            name="read_file",
            description="Lee archivo",
            inputSchema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        ),
        types.Tool(
            name="list_files",
            description="Lista archivos",
            inputSchema={
                "type": "object",
                "properties": {"pattern": {"type": "string", "default": "*"}},
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    log.info("tool invocado", tool=name, args={k: v if k != "content" else f"<{len(v)} chars>" for k, v in arguments.items()})
    try:
        if name == "write_file":
            path = arguments["path"]
            content = arguments["content"]
            fp = safe(path)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")
            size_bytes = fp.stat().st_size
            log.info("archivo escrito", path=path, size_bytes=size_bytes)
            return [types.TextContent(type="text", text=f"ok:{path}")]

        if name == "read_file":
            path = arguments["path"]
            fp = safe(path)
            if not fp.exists():
                log.warning("archivo no encontrado", path=path)
                return [types.TextContent(type="text", text="no encontrado")]
            content = fp.read_text(encoding="utf-8")
            log.info("archivo leído", path=path, size_bytes=len(content.encode()))
            return [types.TextContent(type="text", text=content)]

        if name == "list_files":
            pattern = arguments.get("pattern", "*")
            files = [f.name for f in sorted(WS.glob(pattern)) if f.is_file()]
            log.info("archivos listados", pattern=pattern, count=len(files))
            return [types.TextContent(type="text", text="\n".join(files) or "vacio")]

        log.warning("tool desconocido", tool=name)
        return [types.TextContent(type="text", text=f"err:tool desconocido {name}")]

    except Exception as e:
        log.exception("error en tool", tool=name, error=str(e))
        return [types.TextContent(type="text", text=f"err:{e}")]


async def main():
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())