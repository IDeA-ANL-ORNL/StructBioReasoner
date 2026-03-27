"""MCP Server for StructBioReasoner.

Exposes computational skills, Jnana reasoning endpoints, and Academy
agent status as callable MCP tools. This is the bridge between
OpenClaw (Node.js) and the Python computation layers.

Usage:
    python -m struct_bio_reasoner.mcp.server
"""

import asyncio
import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

# Skills root: <repo>/skills  (two levels up from this file's package dir)
_SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent / "skills"

logger = logging.getLogger(__name__)


def _import_jnana_bridge():
    """Import JnanaReasoningBridge from the hyphenated skills/jnana-reasoning dir."""
    mod_name = "_jnana_reason"
    if mod_name in sys.modules:
        return sys.modules[mod_name].JnanaReasoningBridge
    reason_path = (
        Path(__file__).resolve().parent.parent.parent
        / "skills" / "jnana-reasoning" / "scripts" / "reason.py"
    )
    spec = importlib.util.spec_from_file_location(mod_name, str(reason_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod.JnanaReasoningBridge


class StructBioReasonerMCPServer:
    """MCP server for StructBioReasoner.

    Hosts three categories of endpoints:
    1. Skill tools — invoke computational skills (bindcraft, MD, folding, etc.)
    2. Jnana reasoning — hypothesis generation, parameter bounding, evaluation
    3. Academy status — agent lifecycle, Handle RPC status, exchange health

    On first use, lazily initialises JnanaReasoningBridge (Layer 2) and
    AcademyDispatch (Layer 4).
    """

    def __init__(
        self,
        artifact_store_root: str = "artifact_store",
        academy_config: Optional[Any] = None,
    ) -> None:
        self._tools: dict[str, dict[str, Any]] = {}
        self._artifact_store_root = artifact_store_root

        # Lazy — initialised on first call_tool
        self._reasoning_bridge = None
        self._academy_dispatch = None
        self._academy_config = academy_config

        self._register_tools()

    # ------------------------------------------------------------------
    # Layer 2: Jnana Reasoning Bridge (lazy)
    # ------------------------------------------------------------------

    @property
    def reasoning_bridge(self):
        if self._reasoning_bridge is None:
            JnanaReasoningBridge = _import_jnana_bridge()
            self._reasoning_bridge = JnanaReasoningBridge(
                artifact_store_root=self._artifact_store_root,
            )
        return self._reasoning_bridge

    # ------------------------------------------------------------------
    # Layer 4: Academy Dispatch (lazy)
    # ------------------------------------------------------------------

    @property
    def academy_dispatch(self):
        if self._academy_dispatch is None:
            from struct_bio_reasoner.academy.dispatch import AcademyDispatch
            from struct_bio_reasoner.academy.config import AcademyConfig

            config = self._academy_config or AcademyConfig()
            self._academy_dispatch = AcademyDispatch(config)
        return self._academy_dispatch

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def _register_tools(self) -> None:
        """Register all MCP tool endpoints."""
        # Layer 1: Skill invocation tools
        self._tools["run_skill"] = {
            "name": "run_skill",
            "description": "Invoke a StructBioReasoner computational skill",
            "inputSchema": {
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
        }

        self._tools["list_skills"] = {
            "name": "list_skills",
            "description": "List all available computational skills",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
        }

        # Layer 2: Jnana reasoning tools
        self._tools["jnana_set_goal"] = {
            "name": "jnana_set_goal",
            "description": "Set a research goal for Jnana CoScientist reasoning",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "research_goal": {
                        "type": "string",
                        "description": "The scientific research goal",
                    },
                },
                "required": ["research_goal"],
            },
        }

        self._tools["jnana_generate_hypothesis"] = {
            "name": "jnana_generate_hypothesis",
            "description": "Generate scientific hypotheses via Jnana",
            "inputSchema": {
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
        }

        self._tools["jnana_recommend_action"] = {
            "name": "jnana_recommend_action",
            "description": "Recommend next action via Jnana reasoning (Tier 1)",
            "inputSchema": {
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
        }

        self._tools["jnana_bound_parameters"] = {
            "name": "jnana_bound_parameters",
            "description": "Get Jnana bounded parameter config for a skill (Tier 2)",
            "inputSchema": {
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
        }

        self._tools["jnana_evaluate_results"] = {
            "name": "jnana_evaluate_results",
            "description": "Evaluate experimental results via Jnana",
            "inputSchema": {
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
        }

        self._tools["jnana_check_convergence"] = {
            "name": "jnana_check_convergence",
            "description": "Check if the research goal has been satisfied",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
        }

        # Layer 4: Academy agent status tools
        self._tools["academy_agent_status"] = {
            "name": "academy_agent_status",
            "description": "Get status of Academy agents (Executive/Manager/Worker)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Specific agent ID (optional — returns all if omitted)",
                    },
                },
            },
        }

    def list_tools(self) -> list[dict[str, Any]]:
        """List all registered MCP tools."""
        return list(self._tools.values())

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call an MCP tool by name, routing to the appropriate layer."""
        if name not in self._tools:
            return {"error": f"Unknown tool: {name}"}

        try:
            # Layer 1: Skill invocation → Academy Dispatch
            if name == "run_skill":
                return await self._handle_run_skill(arguments)
            elif name == "list_skills":
                return self._handle_list_skills()

            # Layer 2: Jnana reasoning
            elif name == "jnana_set_goal":
                return self._handle_jnana_set_goal(arguments)
            elif name == "jnana_generate_hypothesis":
                return self._handle_jnana_generate_hypothesis(arguments)
            elif name == "jnana_recommend_action":
                return self._handle_jnana_recommend_action(arguments)
            elif name == "jnana_bound_parameters":
                return self._handle_jnana_bound_parameters(arguments)
            elif name == "jnana_evaluate_results":
                return self._handle_jnana_evaluate_results(arguments)
            elif name == "jnana_check_convergence":
                return self._handle_jnana_check_convergence()

            # Layer 4: Academy status
            elif name == "academy_agent_status":
                return self._handle_academy_status(arguments)

            return {"error": f"Tool '{name}' registered but handler not implemented"}
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            return {"error": str(exc), "tool": name}

    # ------------------------------------------------------------------
    # Layer 1 handlers: skill invocation via Academy Dispatch
    # ------------------------------------------------------------------

    async def _handle_run_skill(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Route a skill invocation to AcademyDispatch."""
        skill_name = arguments["skill_name"]
        params = arguments.get("parameters", {})

        dispatch = self.academy_dispatch
        if not dispatch._started:
            await dispatch.start()

        result = await dispatch.dispatch(skill_name, params)
        return {"tool": "run_skill", "status": "success", "result": result}

    def _handle_list_skills(self) -> dict[str, Any]:
        """List skills by scanning SKILL.md files in the skills/ directory.

        Uses SkillRegistry so that skill discovery works independently of
        whether the Academy/Jnana package is installed, and returns the
        same names that OpenClaw sees when it reads the skills/ tree.
        """
        try:
            from skills._shared.registry import SkillRegistry
            registry = SkillRegistry(_SKILLS_ROOT)
            count = registry.discover()
            skills = [s.to_dict() for s in registry.list_skills()]
        except Exception as exc:
            logger.warning("SkillRegistry discovery failed: %s", exc)
            # Fall back to WORKER_REGISTRY keys so the tool never hard-errors
            skills = self.academy_dispatch.list_available_skills()
            count = len(skills)

        return {
            "tool": "list_skills",
            "status": "success",
            "count": count,
            "skills": skills,
        }

    # ------------------------------------------------------------------
    # Layer 2 handlers: Jnana reasoning
    # ------------------------------------------------------------------

    def _handle_jnana_set_goal(self, arguments: dict[str, Any]) -> dict[str, Any]:
        research_goal = arguments["research_goal"]
        plan = self.reasoning_bridge.set_research_goal(research_goal)
        return {"tool": "jnana_set_goal", "status": "success", "plan": plan.to_dict()}

    def _handle_jnana_generate_hypothesis(self, arguments: dict[str, Any]) -> dict[str, Any]:
        count = arguments.get("count", 1)
        hypotheses = self.reasoning_bridge._generate_hypotheses(count=count)
        return {
            "tool": "jnana_generate_hypothesis",
            "status": "success",
            "hypotheses": [h.to_dict() for h in hypotheses],
        }

    def _handle_jnana_recommend_action(self, arguments: dict[str, Any]) -> dict[str, Any]:
        previous_run_type = arguments.get("previous_run_type", "starting")
        previous_conclusion = arguments.get("previous_conclusion", "")
        rec = self.reasoning_bridge.recommend_next_action(
            previous_run_type=previous_run_type,
            previous_conclusion=previous_conclusion,
        )
        return {"tool": "jnana_recommend_action", "status": "success", "recommendation": rec.to_dict()}

    def _handle_jnana_bound_parameters(self, arguments: dict[str, Any]) -> dict[str, Any]:
        skill_name = arguments["skill_name"]
        task_type = arguments["task_type"]
        config = self.reasoning_bridge.bound_parameters(skill_name, task_type)
        return {"tool": "jnana_bound_parameters", "status": "success", "config": config.to_dict()}

    def _handle_jnana_evaluate_results(self, arguments: dict[str, Any]) -> dict[str, Any]:
        artifact_ids = arguments["artifact_ids"]
        evaluation = self.reasoning_bridge.evaluate_results(artifact_ids)
        return {"tool": "jnana_evaluate_results", "status": "success", "evaluation": evaluation.to_dict()}

    def _handle_jnana_check_convergence(self) -> dict[str, Any]:
        converged = self.reasoning_bridge.check_convergence()
        return {"tool": "jnana_check_convergence", "status": "success", "converged": converged}

    # ------------------------------------------------------------------
    # Layer 4 handlers: Academy agent status
    # ------------------------------------------------------------------

    def _handle_academy_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        dispatch = self.academy_dispatch
        return {
            "tool": "academy_agent_status",
            "status": "success",
            "started": dispatch._started,
            "active_workers": dispatch.list_active_workers(),
            "available_skills": dispatch.list_available_skills(),
        }


def create_server(
    artifact_store_root: str = "artifact_store",
    academy_config: Optional[Any] = None,
) -> StructBioReasonerMCPServer:
    """Create and return an MCP server instance."""
    return StructBioReasonerMCPServer(
        artifact_store_root=artifact_store_root,
        academy_config=academy_config,
    )


def main() -> None:
    """Run the MCP server (stdio transport)."""
    server = create_server()
    logger.info(
        "StructBioReasoner MCP server started with %d tools",
        len(server.list_tools()),
    )
    # Full stdio transport implementation will be added
    # when integrating with the mcp Python SDK
    print(json.dumps({"status": "ready", "tools": len(server.list_tools())}))


if __name__ == "__main__":
    main()
