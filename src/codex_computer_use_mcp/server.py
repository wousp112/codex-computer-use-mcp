from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlparse

import websockets
from mcp.server.fastmcp import FastMCP


ApprovalMode = Literal["known-safe-only", "always", "never"]
ThreadMode = Literal["stateless", "sticky"]


@dataclass(frozen=True)
class Settings:
    server_name: str
    app_server_url: str
    codex_home: Path
    bundled_marketplace: Path
    plugin_name: str
    plugin_id: str
    default_cwd: Path
    auto_start_app_server: bool
    approval_mode: ApprovalMode
    client_name: str
    client_version: str

    @classmethod
    def from_env(cls) -> "Settings":
        codex_home = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser().resolve()
        bundled_marketplace = Path(
            os.environ.get(
                "CODEX_CU_BUNDLED_MARKETPLACE",
                str(codex_home / ".tmp" / "bundled-marketplaces" / "openai-bundled" / ".agents" / "plugins" / "marketplace.json"),
            )
        ).expanduser()
        default_cwd = Path(os.environ.get("CODEX_CU_DEFAULT_CWD", str(Path.home()))).expanduser()
        approval_mode = os.environ.get("CODEX_CU_APPROVAL_MODE", "known-safe-only")
        if approval_mode not in {"known-safe-only", "always", "never"}:
            raise RuntimeError(
                "CODEX_CU_APPROVAL_MODE must be one of: known-safe-only, always, never"
            )
        return cls(
            server_name=os.environ.get("CODEX_CU_SERVER_NAME", "codex-computer-use-mcp"),
            app_server_url=os.environ.get("CODEX_CU_APP_SERVER_URL", "ws://127.0.0.1:8766"),
            codex_home=codex_home,
            bundled_marketplace=bundled_marketplace,
            plugin_name=os.environ.get("CODEX_CU_PLUGIN_NAME", "computer-use"),
            plugin_id=os.environ.get("CODEX_CU_PLUGIN_ID", "computer-use@openai-bundled"),
            default_cwd=default_cwd,
            auto_start_app_server=os.environ.get("CODEX_CU_AUTO_START_APP_SERVER", "1").lower() not in {"0", "false", "no"},
            approval_mode=approval_mode,
            client_name=os.environ.get("CODEX_CU_CLIENT_NAME", "codex-computer-use-mcp"),
            client_version=os.environ.get("CODEX_CU_CLIENT_VERSION", "0.1.0"),
        )


def create_mcp(settings: Optional[Settings] = None) -> FastMCP:
    settings = settings or Settings.from_env()
    mcp = FastMCP(settings.server_name)

    class AppServerClient:
        def __init__(self, config: Settings):
            self.config = config
            self.url = config.app_server_url
            self.ws = None
            self._next_id = 0
            self._spawned_proc: Optional[subprocess.Popen[str]] = None

        @staticmethod
        def _run(cmd: List[str]) -> str:
            proc = subprocess.run(cmd, capture_output=True, text=True)
            return (proc.stdout or "").strip()

        def _local_listener_command_for_url(self, url: str) -> Optional[str]:
            parsed = urlparse(url)
            if parsed.scheme not in {"ws", "wss"}:
                return None
            host = parsed.hostname
            port = parsed.port
            if host not in {"127.0.0.1", "localhost"} or port is None:
                return None
            pid = self._run(["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"])
            if not pid:
                return None
            pid = pid.splitlines()[0].strip()
            return self._run(["ps", "-p", pid, "-o", "command="])

        @staticmethod
        def _is_codex_app_server_command(command: Optional[str]) -> bool:
            if not command:
                return False
            return "codex app-server" in command

        def _assert_backend_is_sane(self, url: str) -> None:
            listener_cmd = self._local_listener_command_for_url(url)
            if listener_cmd and not self._is_codex_app_server_command(listener_cmd):
                raise RuntimeError(
                    "Refusing to connect to the wrong backend. "
                    f"{url} is currently owned by: {listener_cmd!r}. "
                    "This bridge expects a Codex app-server websocket backend on that URL."
                )

        @staticmethod
        def _port_is_open(host: str, port: int) -> bool:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.25)
                return sock.connect_ex((host, port)) == 0

        async def _wait_for_local_listener(self, host: str, port: int, timeout_sec: float = 10.0) -> None:
            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                if self._port_is_open(host, port):
                    return
                await asyncio.sleep(0.2)
            raise TimeoutError(f"Timed out waiting for Codex app-server listener on {host}:{port}")

        def _spawn_local_app_server(self, url: str) -> subprocess.Popen[str]:
            parsed = urlparse(url)
            if parsed.scheme not in {"ws", "wss"} or parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.port is None:
                raise RuntimeError(f"Can only auto-launch a local ws app-server, got {url!r}")
            codex_bin = shutil.which("codex")
            if not codex_bin:
                raise RuntimeError("Cannot auto-launch Codex app-server because `codex` is not on PATH")
            return subprocess.Popen(
                [codex_bin, "app-server", "--listen", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                start_new_session=True,
            )

        def _approval_response(self, params: Dict[str, Any]) -> Dict[str, Any]:
            mode = self.config.approval_mode
            if mode == "never":
                return {"action": "decline", "content": None}
            if mode == "always":
                return {"action": "accept", "content": params.get("requestedSchema") and {} or {}}

            server_name = params.get("serverName")
            request_mode = params.get("mode")
            requested_schema = params.get("requestedSchema") or {}
            if server_name == self.config.plugin_name and request_mode == "form" and requested_schema == {"type": "object", "properties": {}}:
                return {"action": "accept", "content": {}}
            return {"action": "decline", "content": None}

        async def _handle_server_request(self, msg: Dict[str, Any]) -> bool:
            method = msg.get("method")
            req_id = msg.get("id")
            params = msg.get("params", {})
            if req_id is None:
                return False

            if method == "mcpServer/elicitation/request":
                response = self._approval_response(params)
                await self.ws.send(json.dumps({"id": req_id, "result": response}))
                if response["action"] != "accept":
                    message = params.get("message") or "Unknown MCP elicitation request"
                    raise RuntimeError(
                        "Declined MCP elicitation request. "
                        f"server={params.get('serverName')!r} mode={params.get('mode')!r} message={message}"
                    )
                return True

            return False

        async def _recv_json(self) -> Dict[str, Any]:
            while True:
                msg = json.loads(await self.ws.recv())
                if await self._handle_server_request(msg):
                    continue
                return msg

        async def __aenter__(self):
            self._assert_backend_is_sane(self.url)
            parsed = urlparse(self.url)
            if (
                self.config.auto_start_app_server
                and parsed.scheme in {"ws", "wss"}
                and parsed.hostname in {"127.0.0.1", "localhost"}
                and parsed.port is not None
            ):
                if self._local_listener_command_for_url(self.url) is None:
                    self._spawned_proc = self._spawn_local_app_server(self.url)
                    await self._wait_for_local_listener(parsed.hostname, parsed.port)
            self.ws = await websockets.connect(self.url, max_size=2**22)
            await self.call(
                "initialize",
                {
                    "clientInfo": {
                        "name": self.config.client_name,
                        "version": self.config.client_version,
                    },
                    "capabilities": {"experimentalApi": True},
                },
            )
            return self

        async def __aexit__(self, exc_type, exc, tb):
            if self.ws is not None:
                await self.ws.close()
            if self._spawned_proc is not None and self._spawned_proc.poll() is None:
                os.killpg(self._spawned_proc.pid, signal.SIGTERM)
                try:
                    self._spawned_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(self._spawned_proc.pid, signal.SIGKILL)

        async def call(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
            self._next_id += 1
            req_id = self._next_id
            await self.ws.send(json.dumps({"id": req_id, "method": method, "params": params}))
            while True:
                msg = await self._recv_json()
                if msg.get("id") == req_id:
                    if "error" in msg:
                        raise RuntimeError(f"{method} failed: {msg['error']}")
                    return msg["result"]

        async def ensure_plugin_installed(self) -> Dict[str, Any]:
            result = await self.call(
                "plugin/read",
                {
                    "marketplacePath": str(self.config.bundled_marketplace),
                    "pluginName": self.config.plugin_name,
                },
            )
            plugin = result["plugin"]
            if not plugin["summary"].get("installed"):
                await self.call(
                    "plugin/install",
                    {
                        "marketplacePath": str(self.config.bundled_marketplace),
                        "pluginName": self.config.plugin_name,
                    },
                )
                result = await self.call(
                    "plugin/read",
                    {
                        "marketplacePath": str(self.config.bundled_marketplace),
                        "pluginName": self.config.plugin_name,
                    },
                )
                plugin = result["plugin"]
            return plugin

        async def run_computer_use_task(
            self,
            prompt: str,
            cwd: Optional[str] = None,
            timeout_sec: int = 180,
            model: Optional[str] = None,
            effort: Optional[str] = None,
            thread_mode: ThreadMode = "stateless",
            thread_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            await self.ensure_plugin_installed()

            if thread_mode not in {"stateless", "sticky"}:
                raise ValueError("thread_mode must be 'stateless' or 'sticky'")

            resolved_cwd = cwd or str(self.config.default_cwd)
            created_new_thread = False
            if thread_mode == "sticky" and thread_id:
                resolved_thread_id = thread_id
            else:
                thread = await self.call(
                    "thread/start",
                    {"message": "", "cwd": resolved_cwd, "plugins": [self.config.plugin_id]},
                )
                resolved_thread_id = thread["thread"]["id"]
                created_new_thread = True

            turn_params: Dict[str, Any] = {
                "threadId": resolved_thread_id,
                "input": [{"type": "text", "text": prompt}],
                "approvalPolicy": {
                    "granular": {
                        "mcp_elicitations": True,
                        "request_permissions": False,
                        "rules": False,
                        "sandbox_approval": False,
                        "skill_approval": False,
                    }
                },
                "approvalsReviewer": "user",
                "cwd": resolved_cwd,
            }
            if model is not None:
                turn_params["model"] = model
            if effort is not None:
                turn_params["effort"] = effort

            turn = await self.call("turn/start", turn_params)
            turn_id = turn["turn"]["id"]

            final_answer: Optional[str] = None
            commentary_parts: List[str] = []
            startup_events: List[Dict[str, Any]] = []
            tool_failures: List[Dict[str, Any]] = []
            deadline = time.time() + timeout_sec

            while time.time() < deadline:
                remaining = deadline - time.time()
                msg = await asyncio.wait_for(self._recv_json(), timeout=max(1, remaining))
                method = msg.get("method")
                params = msg.get("params", {})
                if not method:
                    continue

                if method == "mcpServer/startupStatus/updated":
                    startup_events.append(params)
                    continue

                if params.get("threadId") != resolved_thread_id:
                    continue

                if method == "item/completed":
                    item = params.get("item", {})
                    if item.get("type") == "agentMessage":
                        text = item.get("text") or ""
                        phase = item.get("phase")
                        if phase == "final_answer":
                            final_answer = text
                        elif phase == "commentary" and text:
                            commentary_parts.append(text)
                    elif item.get("type") == "mcpToolCall" and item.get("status") == "failed":
                        tool_failures.append(
                            {
                                "server": item.get("server"),
                                "tool": item.get("tool"),
                                "arguments": item.get("arguments"),
                                "error": item.get("error"),
                                "duration_ms": item.get("durationMs"),
                            }
                        )
                elif method == "turn/completed":
                    turn_info = params.get("turn", {})
                    if turn_info.get("id") == turn_id:
                        if turn_info.get("status") != "completed" and tool_failures:
                            raise RuntimeError(
                                f"Codex turn ended with status={turn_info.get('status')!r}; tool_failures={json.dumps(tool_failures, ensure_ascii=False)}"
                            )
                        return {
                            "thread_id": resolved_thread_id,
                            "turn_id": turn_id,
                            "final_answer": final_answer,
                            "commentary": commentary_parts,
                            "startup_events": startup_events,
                            "tool_failures": tool_failures,
                            "status": turn_info.get("status"),
                            "thread_mode": thread_mode,
                            "created_new_thread": created_new_thread,
                            "model": model,
                            "effort": effort,
                            "cwd": resolved_cwd,
                            "app_server_url": self.config.app_server_url,
                        }

            timeout_detail = f"Timed out waiting for Codex turn completion after {timeout_sec}s"
            if tool_failures:
                timeout_detail += f"; tool_failures={json.dumps(tool_failures, ensure_ascii=False)}"
            raise TimeoutError(timeout_detail)

    @mcp.tool()
    async def codex_computer_use_run(
        prompt: str,
        cwd: Optional[str] = None,
        timeout_sec: int = 180,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        thread_mode: ThreadMode = "stateless",
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run a task through Codex Desktop with the Computer Use plugin enabled."""
        async with AppServerClient(settings) as client:
            return await client.run_computer_use_task(
                prompt=prompt,
                cwd=cwd,
                timeout_sec=timeout_sec,
                model=model,
                effort=effort,
                thread_mode=thread_mode,
                thread_id=thread_id,
            )

    @mcp.tool()
    async def codex_computer_use_status() -> Dict[str, Any]:
        """Check whether Codex Desktop's bundled Computer Use plugin is available."""
        async with AppServerClient(settings) as client:
            plugin = await client.ensure_plugin_installed()
            return {
                "plugin_id": plugin["summary"]["id"],
                "plugin_name": settings.plugin_name,
                "installed": plugin["summary"].get("installed"),
                "enabled": plugin["summary"].get("enabled"),
                "mcp_servers": plugin.get("mcpServers", []),
                "source_path": plugin["summary"]["source"].get("path"),
                "marketplace_path": str(settings.bundled_marketplace),
                "app_server_url": settings.app_server_url,
                "approval_mode": settings.approval_mode,
            }

    return mcp


def main() -> None:
    settings = Settings.from_env()
    create_mcp(settings).run("stdio")


if __name__ == "__main__":
    main()
