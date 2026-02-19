from academy.agent import Agent, action
from academy.manager import Manager
import asyncio
import importlib
import logging
import parsl
import time
import uuid
from parsl import Config
from pathlib import Path
from typing import Any, Optional, Literal

from pydantic import BaseModel
from struct_bio_reasoner.agents.data.events import EventType
from struct_bio_reasoner.utils.parsl_settings import (
    BaseComputeSettings,
    resource_summary_from_config,
)


class AgentRegistry(BaseModel):
    reasoner: str = 'struct_bio_reasoner.agents.language_model.pydantic_ai_agent:ReasonerAgent'
    bindcraft: str = 'struct_bio_reasoner.agents.computational_design.bindcraft_coordinator:BindCraftCoordinator'
    md: str = 'struct_bio_reasoner.agents.molecular_dynamics.MD:MDAgent'
    mmpbsa: str = 'struct_bio_reasoner.agents.molecular_dynamics.mmpbsa_agent:FEAgent'
    folding: str = 'struct_bio_reasoner.agents.structure_prediction.chai_agent:ChaiAgent'
    data: str = 'struct_bio_reasoner.agents.data.data_agent:DataAgent'

    # Maps TaskName values from the LLM to agent registry labels
    # Note: 'data' is intentionally absent — it is infrastructure, not a task target
    TASK_TO_AGENT: dict[str, str] = {
        'computational_design': 'bindcraft',
        'molecular_dynamics': 'md',
        'structure_prediction': 'folding',
        'free_energy': 'mmpbsa',
        'rag': 'reasoner',
        'analysis': 'reasoner',
    }

    def resolve_task(self, task_name) -> str:
        """Translate a TaskName value to an agent registry label."""
        key = task_name.value if hasattr(task_name, 'value') else task_name
        return self.TASK_TO_AGENT.get(key, key)

    def get(self, label: str) -> type:
        path = getattr(self, label)
        module_path, class_name = path.split(':')
        return getattr(importlib.import_module(module_path), class_name)

    def available(self) -> list[str]:
        return list(type(self).model_fields.keys())

class Director(Agent):
    def __init__(self,
                 runtime_config: dict[str, Any],
                 parsl_config: Config | BaseComputeSettings,):
        self.runtime_config = runtime_config
        self.parsl_config = parsl_config
        self.agent_registry = AgentRegistry()

        self.previous_run = 'starting'
        self.history = []
        self._iteration = 0
        self._director_id = runtime_config.get(
            'director_id', str(uuid.uuid4())
        )

        # Derive a resource summary for LLM prompts
        if isinstance(parsl_config, BaseComputeSettings):
            self.resource_summary = parsl_config.resource_summary()
        elif 'parsl' in runtime_config:
            self.resource_summary = resource_summary_from_config(
                runtime_config['parsl']
            )
        else:
            self.resource_summary = ""

        self.logger = logging.getLogger(__name__)

        super().__init__()

    async def agent_on_startup(self) -> None:
        self.dfk = parsl.load(self.parsl_config)
        await self.load_agents()

    async def agent_on_shutdown(self):
        if self.dfk:
            self.dfk.cleanup()
            self.dfk = None

        parsl.clear()

    async def load_agents(self):
        """"""
        self.agents = {}
        self.target_protein = self.runtime_config.get('reasoner', {}).get('target_protein', '')
        available_agents = self.agent_registry.available()
        for agent, kwargs in self.runtime_config.items():
            if agent in available_agents and agent != 'data':
                # Inject target_protein into agents that need it
                if agent == 'bindcraft':
                    kwargs = {**kwargs, 'target_sequence': self.target_protein}
                # Inject resource summary into the reasoner
                if agent == 'reasoner':
                    kwargs = {**kwargs, 'resource_summary': self.resource_summary}
                self.agents[agent] = await self.agent_launch_alongside(
                    self.agent_registry.get(agent),
                    args=None,
                    kwargs=kwargs,
                )

        # Launch the DataAgent for DB persistence
        data_kwargs = self.runtime_config.get('data', {})
        data_kwargs.setdefault(
            'database_url',
            self.runtime_config.get('database_url', 'sqlite+aiosqlite:///data.db'),
        )
        self.agents['data'] = await self.agent_launch_alongside(
            self.agent_registry.get('data'),
            args=None,
            kwargs=data_kwargs,
        )

        self.logger.info(f'Loaded {len(self.agents)} agents!')

    @action
    async def agentic_test(self) -> tuple[str, Any]:
        """Test main loop"""
        previous_run = 'starting'
        results = {'results': 'none'}
        history = ''

        reasoner_input = {
            'results': results,
            'previous_run': previous_run,
            'history': history,
        }
        tool, plan = await self.query_reasoner(reasoner_input)
        self.logger.info(f"Next task: {tool}")

        results = await self.tool_call(tool, plan)

        return tool, results

    @action
    async def agentic_run(self):
        """Main while loop logic"""
        results = {'results': 'none'}
        while True:
            reasoner_input = {
                'results': results,
                'previous_run': self.previous_run,
                'history': self.history,
            }

            tool, plan = await self.query_reasoner(reasoner_input) # gets prompt for tool call

            results = await self.tool_call(tool, plan) # do tool call

    async def _emit(self, event: dict[str, Any]) -> None:
        """Fire-and-forget an event to the DataAgent.

        Failures are logged but never block the Director loop.
        """
        try:
            await self.agents['data'].record_event(event)
        except Exception:
            self.logger.debug("DataAgent event emission failed", exc_info=True)

    async def query_reasoner(self,
                             data: dict[str, Any]) -> tuple[str, BaseModel]:
        self._iteration += 1

        # ── Step 1: generate_recommendation (LLM call) ──
        rec_call_id = str(uuid.uuid4())
        t0 = time.monotonic()

        recommendation = await self.agents['reasoner'].generate_recommendation(
            results=data['results'],
            previous_run=data['previous_run'],
            history=data['history'],
        )

        rec_ms = int((time.monotonic() - t0) * 1000)
        rec = recommendation.recommendation

        await self._emit({
            "event_type": EventType.LLM_CALL.value,
            "director_id": self._director_id,
            "payload": {
                "call_id": rec_call_id,
                "call_type": "recommendation",
                "latency_ms": rec_ms,
                "parsed_output": rec.model_dump()
                    if isinstance(rec, BaseModel) else rec,
            },
        })

        # ── Decision event ──
        decision_id = str(uuid.uuid4())
        await self._emit({
            "event_type": EventType.DECISION.value,
            "director_id": self._director_id,
            "payload": {
                "decision_id": decision_id,
                "llm_call_id": rec_call_id,
                "iteration": self._iteration,
                "previous_task": data['previous_run'],
                "next_task": str(rec.next_task),
                "change_parameters": rec.change_parameters,
                "rationale": rec.rationale,
            },
        })

        # ── Step 2: plan_run (LLM call) ──
        plan_call_id = str(uuid.uuid4())
        t0 = time.monotonic()

        config = await self.agents['reasoner'].plan_run(
            recommendation=recommendation,
            history=data['history']
        )

        plan_ms = int((time.monotonic() - t0) * 1000)

        await self._emit({
            "event_type": EventType.LLM_CALL.value,
            "director_id": self._director_id,
            "payload": {
                "call_id": plan_call_id,
                "call_type": "plan",
                "latency_ms": plan_ms,
                "parsed_output": config.model_dump()
                    if isinstance(config, BaseModel) else config,
            },
        })

        # ── Plan event ──
        plan_config = (
            config.new_config.model_dump()
            if isinstance(config, BaseModel) and hasattr(config, 'new_config')
            else config.model_dump() if isinstance(config, BaseModel)
            else config
        )
        plan_id = str(uuid.uuid4())
        await self._emit({
            "event_type": EventType.PLAN.value,
            "director_id": self._director_id,
            "payload": {
                "plan_id": plan_id,
                "decision_id": decision_id,
                "llm_call_id": plan_call_id,
                "task_type": str(rec.next_task),
                "plan_model_name": type(config).__name__,
                "plan_config": plan_config,
                "rationale": getattr(config, 'rationale', ''),
            },
        })

        self.previous_run = data['previous_run']
        self.history.append(data['history'])

        # Stash plan_id for tool_call to reference
        self._last_plan_id = plan_id

        return recommendation.recommendation.next_task, config

    async def tool_call(self,
                        tool: str,
                        plan: BaseModel | dict[str, Any]):
        """Access correct subagent based on the `tool` key. Pass in
        the inputs in the form of **kwargs."""
        agent_key = self.agent_registry.resolve_task(tool)

        # Extract the nested config — plan may arrive as a Pydantic model
        # or as a plain dict after Academy serialization
        if isinstance(plan, BaseModel):
            config = plan.new_config if hasattr(plan, 'new_config') else plan
            kwargs = config.model_dump() if isinstance(config, BaseModel) else config
        elif isinstance(plan, dict):
            config = plan.get('new_config', plan)
            kwargs = config.model_dump() if isinstance(config, BaseModel) else config
        else:
            kwargs = plan

        self.logger.debug(f"tool_call: agent_key={agent_key}, kwargs={kwargs}")

        # ── Emit EXECUTION_START ──
        execution_id = str(uuid.uuid4())
        plan_id = getattr(self, '_last_plan_id', None)

        await self._emit({
            "event_type": EventType.EXECUTION_START.value,
            "director_id": self._director_id,
            "payload": {
                "execution_id": execution_id,
                "plan_id": plan_id,
                "agent_key": agent_key,
                "input_kwargs": kwargs,
            },
        })

        t0 = time.monotonic()
        error_msg = None
        status = "completed"
        results = None

        try:
            results = await self.agents[agent_key].run(**kwargs)
        except Exception as exc:
            error_msg = str(exc)
            status = "failed"
            raise
        finally:
            duration_ms = int((time.monotonic() - t0) * 1000)

            # Serialise results for the DB (best-effort)
            try:
                result_data = (
                    results.model_dump()
                    if isinstance(results, BaseModel)
                    else results
                )
            except Exception:
                result_data = str(results) if results is not None else None

            await self._emit({
                "event_type": EventType.EXECUTION_END.value,
                "director_id": self._director_id,
                "payload": {
                    "execution_id": execution_id,
                    "status": status,
                    "result_data": result_data,
                    "error": error_msg,
                    "duration_ms": duration_ms,
                },
            })

        return results

    @action
    async def executive_reasoning(self,
                                  prompt: str):
        """Hook into the reasoning agent for the executive agent.
        """
        response = await self.agents['reasoner'].query()

    @action
    async def check_status(self) -> str:
        """"""
        status = await self.agents['reasoner'].evaluate_history(self.history)
        return status

    @action
    async def receive_instruction(self,
                                  instruction: str):
        """Receive instructions from Executive agent. Utilize this in the next
        reasoning trace to guide next task(s)."""
        # Somehow incorporate a signal from upstream reasoning into the next task
        pass
