"""MCP Server for StructBioReasoner.

Exposes computational skills, Jnana reasoning endpoints, Academy agent
status, and human-in-the-loop directives as callable MCP tools.  This is
the bridge between any MCP client (OpenClaw, Claude Code, a web UI) and
the Python computation layers.

The server uses the official ``mcp`` Python SDK with stdio transport so
that it can be launched as a subprocess by any MCP-compatible host:

    python -m struct_bio_reasoner.mcp.server

Configuration for OpenClaw lives in ``.openclaw.json`` at the repo root.
"""

import asyncio
import importlib.util
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Jnana bridge import helper (handles hyphenated skill directory)
# ---------------------------------------------------------------------------


def _import_jnana_bridge():
    """Import JnanaReasoningBridge from skills/jnana-reasoning/scripts/reason.py."""
    mod_name = "_jnana_reason"
    if mod_name in sys.modules:
        return sys.modules[mod_name].JnanaReasoningBridge
    reason_path = (
        Path(__file__).resolve().parent.parent.parent
        / "skills"
        / "jnana-reasoning"
        / "scripts"
        / "reason.py"
    )
    if not reason_path.exists():
        raise FileNotFoundError(
            f"Jnana reasoning script not found at {reason_path}. "
            "Ensure the skills/jnana-reasoning directory is present."
        )
    spec = importlib.util.spec_from_file_location(mod_name, str(reason_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod.JnanaReasoningBridge


# ---------------------------------------------------------------------------
# Shared application state (lazy-initialised, lives for the server lifetime)
# ---------------------------------------------------------------------------


class _AppState:
    """Holds lazily-initialised singletons shared across tool handlers."""

    def __init__(
        self,
        artifact_store_root: str = "artifact_store",
        academy_config: Optional[Any] = None,
    ) -> None:
        self._artifact_store_root = artifact_store_root
        self._academy_config = academy_config

        self._reasoning_bridge = None
        self._academy_dispatch = None

        # Human-in-the-loop directive inbox
        self._directives: list[dict[str, Any]] = []

        # Lightweight campaign status tracking
        self._campaign_started_at: Optional[float] = None
        self._tasks_submitted: int = 0
        self._tasks_completed: int = 0
        self._research_goal: Optional[str] = None

        # Priority frontier (lazy — created when orchestration is available)
        self._frontier = None

    # -- Layer 2: Jnana Reasoning Bridge (lazy) ----------------------------

    @property
    def reasoning_bridge(self):
        if self._reasoning_bridge is None:
            JnanaReasoningBridge = _import_jnana_bridge()
            self._reasoning_bridge = JnanaReasoningBridge(
                artifact_store_root=self._artifact_store_root,
            )
        return self._reasoning_bridge

    # -- Layer 4: Academy Dispatch (lazy) ----------------------------------

    @property
    def academy_dispatch(self):
        if self._academy_dispatch is None:
            from struct_bio_reasoner.academy.config import AcademyConfig
            from struct_bio_reasoner.academy.dispatch import AcademyDispatch

            config = self._academy_config or AcademyConfig()
            self._academy_dispatch = AcademyDispatch(config)
        return self._academy_dispatch

    # -- Directive inbox ---------------------------------------------------

    def add_directive(self, directive: dict[str, Any]) -> None:
        directive.setdefault("timestamp", time.time())
        self._directives.append(directive)

    def pop_directives(self) -> list[dict[str, Any]]:
        """Return and clear all pending directives."""
        out = list(self._directives)
        self._directives.clear()
        return out

    def peek_directives(self) -> list[dict[str, Any]]:
        return list(self._directives)


# ---------------------------------------------------------------------------
# Tool definitions (schemas)
# ---------------------------------------------------------------------------

TOOLS: list[Tool] = [
    # -- Layer 1: Skill invocation -----------------------------------------
    Tool(
        name="run_skill",
        description=(
            "Invoke a StructBioReasoner computational skill (bindcraft, "
            "molecular-dynamics, structure-prediction, etc.).  The skill "
            "runs on HPC via Academy dispatch and returns results as an "
            "artifact."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Name of the skill to invoke",
                },
                "parameters": {
                    "type": "object",
                    "description": "Skill-specific parameters",
                },
            },
            "required": ["skill_name"],
        },
    ),
    Tool(
        name="list_skills",
        description="List all available computational skills and their descriptions.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # -- Layer 2: Jnana reasoning ------------------------------------------
    Tool(
        name="jnana_set_goal",
        description=(
            "Set the research goal that drives all subsequent reasoning. "
            "Must be called before recommend_action or bound_parameters."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "research_goal": {
                    "type": "string",
                    "description": "The scientific research goal",
                },
            },
            "required": ["research_goal"],
        },
    ),
    Tool(
        name="jnana_generate_hypothesis",
        description="Generate scientific hypotheses for the current research goal.",
        inputSchema={
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of hypotheses to generate",
                    "default": 1,
                },
                "strategies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Hypothesis generation strategies",
                },
            },
        },
    ),
    Tool(
        name="jnana_recommend_action",
        description=(
            "Tier-1 reasoning: recommend the next task type to run "
            "(e.g. computational_design, molecular_dynamics, analysis, stop)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "previous_run_type": {
                    "type": "string",
                    "description": "Type of the previous run",
                    "default": "starting",
                },
                "previous_conclusion": {
                    "type": "string",
                    "description": "Conclusion from the previous run",
                    "default": "",
                },
            },
        },
    ),
    Tool(
        name="jnana_bound_parameters",
        description=(
            "Tier-2 reasoning: generate a bounded parameter configuration "
            "for a specific skill and task type."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Target skill name",
                },
                "task_type": {
                    "type": "string",
                    "description": "Task type for parameter bounding",
                },
            },
            "required": ["skill_name", "task_type"],
        },
    ),
    Tool(
        name="jnana_evaluate_results",
        description="Evaluate experimental results stored as artifacts against the current hypotheses.",
        inputSchema={
            "type": "object",
            "properties": {
                "artifact_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Artifact IDs to evaluate",
                },
            },
            "required": ["artifact_ids"],
        },
    ),
    Tool(
        name="jnana_check_convergence",
        description="Check whether the research goal has been satisfied and the campaign can stop.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # -- Layer 4: Academy status -------------------------------------------
    Tool(
        name="academy_agent_status",
        description="Get the status of Academy agents (Executive/Manager/Worker).",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Specific agent ID (optional — returns all if omitted)",
                },
            },
        },
    ),
    # -- Human-in-the-loop -------------------------------------------------
    Tool(
        name="send_directive",
        description=(
            "Send a human directive to steer the running campaign. "
            "Directives are injected into the reasoner's context on "
            "its next decision cycle.  Use this to change focus "
            "(e.g. 'focus on hydrophobic hotspots'), adjust parameters "
            "(e.g. 'increase MD simulation length to 100ns'), reprioritize "
            "tasks, or request early stopping."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "directive": {
                    "type": "string",
                    "description": "Free-text instruction to the reasoner",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "normal", "high", "urgent"],
                    "description": "How urgently this should affect the campaign",
                    "default": "normal",
                },
                "category": {
                    "type": "string",
                    "enum": [
                        "focus_change",
                        "parameter_override",
                        "add_constraint",
                        "remove_constraint",
                        "reprioritize",
                        "stop",
                        "other",
                    ],
                    "description": "Category of the directive",
                    "default": "other",
                },
            },
            "required": ["directive"],
        },
    ),
    Tool(
        name="get_campaign_status",
        description=(
            "Get the current status of the running campaign: research goal, "
            "tasks submitted/completed, pending human directives, and "
            "elapsed time."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_pending_directives",
        description=(
            "View all pending human directives that have not yet been "
            "consumed by the reasoner."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    # -- Orchestration: queue status and control ---------------------------
    Tool(
        name="get_queue_status",
        description=(
            "Get the status of the HPC task queue: pending/running counts, "
            "per-executor breakdown, and currently running tools."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="reprioritize_task",
        description=(
            "Change the priority of a pending task in the queue.  Lower "
            "numbers = higher priority (0=critical, 1=high, 2=default, 3=low)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "ID of the pending task to reprioritize",
                },
                "new_priority": {
                    "type": "integer",
                    "description": "New priority (0=critical, 1=high, 2=default, 3=low)",
                },
            },
            "required": ["task_id", "new_priority"],
        },
    ),
    Tool(
        name="cancel_task",
        description="Cancel a pending (not yet running) task by its task_id.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "ID of the pending task to cancel",
                },
            },
            "required": ["task_id"],
        },
    ),
]


# ---------------------------------------------------------------------------
# Backwards-compatible wrapper (used by tests and direct Python callers)
# ---------------------------------------------------------------------------


class StructBioReasonerMCPServer:
    """Compatibility wrapper providing the pre-MCP-SDK interface.

    Tests and direct Python callers use ``create_server()`` which returns
    this object.  It delegates to ``_AppState`` for state and ``_dispatch``
    for tool handling, so behaviour is identical to the real MCP transport.
    """

    def __init__(
        self,
        artifact_store_root: str = "artifact_store",
        academy_config: Optional[Any] = None,
    ) -> None:
        self._state = _AppState(
            artifact_store_root=artifact_store_root,
            academy_config=academy_config,
        )

    # Expose state properties for test mocking
    @property
    def reasoning_bridge(self):
        return self._state.reasoning_bridge

    @property
    def academy_dispatch(self):
        return self._state.academy_dispatch

    @property
    def _academy_dispatch(self):
        return self._state._academy_dispatch

    @_academy_dispatch.setter
    def _academy_dispatch(self, value):
        self._state._academy_dispatch = value

    def list_tools(self) -> list[dict[str, Any]]:
        """List tools as plain dicts (old interface)."""
        return [
            {"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
            for t in TOOLS
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool and return the result dict directly."""
        return await _dispatch(self._state, name, arguments)


# ---------------------------------------------------------------------------
# Build the MCP Server
# ---------------------------------------------------------------------------


def _build_server(state: _AppState) -> Server:
    """Wire tool definitions and handlers onto an ``mcp.Server``."""

    app = Server(
        name="structbioreasoner",
        version="0.1.0",
        instructions=(
            "StructBioReasoner: AI-powered protein engineering platform. "
            "Set a research goal with jnana_set_goal, then use "
            "jnana_recommend_action and run_skill in a loop.  Use "
            "send_directive at any time to steer the campaign."
        ),
    )

    # -- list_tools --------------------------------------------------------

    @app.list_tools()
    async def handle_list_tools() -> list[Tool]:
        return TOOLS

    # -- call_tool ---------------------------------------------------------

    @app.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[TextContent]:
        arguments = arguments or {}
        try:
            result = await _dispatch(state, name, arguments)
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            result = {"error": str(exc), "tool": name}
        return [TextContent(type="text", text=json.dumps(result, default=str))]

    return app


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------


async def _dispatch(
    state: _AppState, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Route a tool call to the appropriate handler."""

    # -- Layer 1: Skill invocation -----------------------------------------

    if name == "run_skill":
        skill_name = arguments["skill_name"]
        params = arguments.get("parameters", {})
        dispatch = state.academy_dispatch
        if not dispatch._started:
            await dispatch.start()
        state._tasks_submitted += 1
        result = await dispatch.dispatch(skill_name, params)
        state._tasks_completed += 1
        return {"tool": "run_skill", "status": "success", "result": result}

    if name == "list_skills":
        return {
            "tool": "list_skills",
            "status": "success",
            "skills": state.academy_dispatch.list_available_skills(),
        }

    # -- Layer 2: Jnana reasoning ------------------------------------------

    if name == "jnana_set_goal":
        research_goal = arguments["research_goal"]
        state._research_goal = research_goal
        state._campaign_started_at = time.time()
        plan = state.reasoning_bridge.set_research_goal(research_goal)
        return {
            "tool": "jnana_set_goal",
            "status": "success",
            "plan": plan.to_dict(),
        }

    if name == "jnana_generate_hypothesis":
        count = arguments.get("count", 1)
        hypotheses = state.reasoning_bridge._generate_hypotheses(count=count)
        return {
            "tool": "jnana_generate_hypothesis",
            "status": "success",
            "hypotheses": [h.to_dict() for h in hypotheses],
        }

    if name == "jnana_recommend_action":
        previous_run_type = arguments.get("previous_run_type", "starting")
        previous_conclusion = arguments.get("previous_conclusion", "")
        # Inject pending human directives into the conclusion context
        pending = state.pop_directives()
        if pending:
            directive_text = "\n".join(
                f"[HUMAN DIRECTIVE ({d.get('priority', 'normal')})]: {d['directive']}"
                for d in pending
            )
            previous_conclusion = (
                f"{previous_conclusion}\n\n"
                f"--- Human directives received ---\n{directive_text}"
            ).strip()
        rec = state.reasoning_bridge.recommend_next_action(
            previous_run_type=previous_run_type,
            previous_conclusion=previous_conclusion,
        )
        return {
            "tool": "jnana_recommend_action",
            "status": "success",
            "recommendation": rec.to_dict(),
            "directives_applied": len(pending),
        }

    if name == "jnana_bound_parameters":
        skill_name = arguments["skill_name"]
        task_type = arguments["task_type"]
        config = state.reasoning_bridge.bound_parameters(skill_name, task_type)
        return {
            "tool": "jnana_bound_parameters",
            "status": "success",
            "config": config.to_dict(),
        }

    if name == "jnana_evaluate_results":
        artifact_ids = arguments["artifact_ids"]
        evaluation = state.reasoning_bridge.evaluate_results(artifact_ids)
        return {
            "tool": "jnana_evaluate_results",
            "status": "success",
            "evaluation": evaluation.to_dict(),
        }

    if name == "jnana_check_convergence":
        converged = state.reasoning_bridge.check_convergence()
        return {
            "tool": "jnana_check_convergence",
            "status": "success",
            "converged": converged,
        }

    # -- Layer 4: Academy status -------------------------------------------

    if name == "academy_agent_status":
        dispatch = state.academy_dispatch
        return {
            "tool": "academy_agent_status",
            "status": "success",
            "started": dispatch._started,
            "active_workers": dispatch.list_active_workers(),
            "available_skills": dispatch.list_available_skills(),
        }

    # -- Human-in-the-loop -------------------------------------------------

    if name == "send_directive":
        directive = {
            "directive": arguments["directive"],
            "priority": arguments.get("priority", "normal"),
            "category": arguments.get("category", "other"),
        }
        state.add_directive(directive)
        return {
            "tool": "send_directive",
            "status": "accepted",
            "directive": directive,
            "pending_count": len(state.peek_directives()),
        }

    if name == "get_campaign_status":
        elapsed = (
            time.time() - state._campaign_started_at
            if state._campaign_started_at
            else 0.0
        )
        return {
            "tool": "get_campaign_status",
            "status": "success",
            "research_goal": state._research_goal,
            "campaign_active": state._campaign_started_at is not None,
            "elapsed_seconds": round(elapsed, 1),
            "tasks_submitted": state._tasks_submitted,
            "tasks_completed": state._tasks_completed,
            "pending_directives": len(state.peek_directives()),
        }

    if name == "get_pending_directives":
        return {
            "tool": "get_pending_directives",
            "status": "success",
            "directives": state.peek_directives(),
        }

    # -- Orchestration: queue control --------------------------------------

    if name == "get_queue_status":
        if state._frontier is not None:
            return {
                "tool": "get_queue_status",
                "status": "success",
                **state._frontier.status_snapshot(),
            }
        return {
            "tool": "get_queue_status",
            "status": "success",
            "pending": 0,
            "running": 0,
            "is_empty": True,
            "note": "No frontier active — tasks dispatched directly via Academy",
        }

    if name == "reprioritize_task":
        task_id = arguments["task_id"]
        new_priority = arguments["new_priority"]
        if state._frontier is not None:
            ok = state._frontier.reprioritize(task_id, new_priority)
            return {
                "tool": "reprioritize_task",
                "status": "success" if ok else "not_found",
                "task_id": task_id,
                "new_priority": new_priority,
            }
        return {
            "tool": "reprioritize_task",
            "status": "error",
            "reason": "No frontier active",
        }

    if name == "cancel_task":
        task_id = arguments["task_id"]
        if state._frontier is not None:
            ok = state._frontier.cancel_pending(task_id)
            return {
                "tool": "cancel_task",
                "status": "cancelled" if ok else "not_found",
                "task_id": task_id,
            }
        return {
            "tool": "cancel_task",
            "status": "error",
            "reason": "No frontier active",
        }

    return {"error": f"Unknown tool: {name}"}


# ---------------------------------------------------------------------------
# Factory and entry point
# ---------------------------------------------------------------------------


def create_server(
    artifact_store_root: str = "artifact_store",
    academy_config: Optional[Any] = None,
) -> StructBioReasonerMCPServer:
    """Create a server wrapper for direct Python use and testing.

    Returns a :class:`StructBioReasonerMCPServer` that exposes
    ``list_tools()`` and ``call_tool()`` without needing MCP transport.
    """
    return StructBioReasonerMCPServer(
        artifact_store_root=artifact_store_root,
        academy_config=academy_config,
    )


def create_mcp_app(
    artifact_store_root: str = "artifact_store",
    academy_config: Optional[Any] = None,
) -> tuple[Server, _AppState]:
    """Create the real MCP ``Server`` for stdio transport."""
    state = _AppState(
        artifact_store_root=artifact_store_root,
        academy_config=academy_config,
    )
    app = _build_server(state)
    return app, state


def main() -> None:
    """Run the MCP server over stdio transport."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,  # MCP uses stdout for protocol; logs go to stderr
    )

    app, _state = create_mcp_app()

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )

    asyncio.run(_run())


if __name__ == "__main__":
    main()
