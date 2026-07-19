from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from app.schemas import AgentFinding, AgentProgressEvent, RiskAssessment
from app.services.agent_workflow.base import AgentContext
from app.services.agent_workflow.coordinator import CoordinatorAgent
from app.services.agent_workflow.emergency import EmergencyPlanningAgent
from app.services.agent_workflow.flood import FloodAgent
from app.services.agent_workflow.infrastructure import InfrastructureAgent
from app.services.agent_workflow.routing import RoutingAgent
from app.services.agent_workflow.weather import WeatherAgent

ProgressCallback = Callable[[AgentProgressEvent], Awaitable[None]]


class IndependentAgent(Protocol):
    name: str

    async def run(self, context: AgentContext) -> AgentFinding: ...


@dataclass(frozen=True)
class WorkflowOutput:
    risk: RiskAssessment
    findings: list[AgentFinding]


class AsyncAgentWorkflow:
    """Runs independent specialists concurrently, then coordinates dependent work."""

    def __init__(self) -> None:
        self._independent_agents: list[IndependentAgent] = [
            WeatherAgent(),
            FloodAgent(),
            InfrastructureAgent(),
            RoutingAgent(),
        ]
        self._emergency_agent = EmergencyPlanningAgent()
        self._coordinator_agent = CoordinatorAgent()

    async def run(
        self, context: AgentContext, publish: ProgressCallback | None = None
    ) -> WorkflowOutput:
        findings = list(
            await asyncio.gather(
                *(self._run_independent(agent, context, publish) for agent in self._independent_agents)
            )
        )
        emergency = await self._run_dependent(self._emergency_agent, context, findings, publish)
        findings.append(emergency)
        risk, coordinator = await self._run_coordinator(context, findings, publish)
        findings.append(coordinator)
        return WorkflowOutput(risk=risk, findings=findings)

    async def _run_independent(
        self, agent: IndependentAgent, context: AgentContext, publish: ProgressCallback | None
    ) -> AgentFinding:
        await self._publish(publish, agent.name, "running", "Analyzing shared assessment evidence.")
        started = perf_counter()
        try:
            finding = await asyncio.wait_for(agent.run(context), timeout=5)
            duration_ms = round((perf_counter() - started) * 1_000)
            finding = finding.model_copy(update={"duration_ms": duration_ms})
            await self._publish(publish, agent.name, "complete", finding.summary, duration_ms)
            return finding
        except Exception:
            duration_ms = round((perf_counter() - started) * 1_000)
            finding = AgentFinding(
                agent=agent.name,
                status="degraded",
                summary="Agent was unavailable; the Coordinator will continue with partial evidence.",
                duration_ms=duration_ms,
            )
            await self._publish(publish, agent.name, "degraded", finding.summary, duration_ms)
            return finding

    async def _run_dependent(
        self,
        agent: EmergencyPlanningAgent,
        context: AgentContext,
        findings: list[AgentFinding],
        publish: ProgressCallback | None,
    ) -> AgentFinding:
        await self._publish(publish, agent.name, "running", "Preparing human-review priorities.")
        started = perf_counter()
        try:
            finding = await asyncio.wait_for(agent.run(context, findings), timeout=5)
            duration_ms = round((perf_counter() - started) * 1_000)
            finding = finding.model_copy(update={"duration_ms": duration_ms})
            await self._publish(publish, agent.name, "complete", finding.summary, duration_ms)
            return finding
        except Exception:
            duration_ms = round((perf_counter() - started) * 1_000)
            finding = AgentFinding(
                agent=agent.name,
                status="degraded",
                summary="Emergency planning was unavailable; human review remains required.",
                duration_ms=duration_ms,
            )
            await self._publish(publish, agent.name, "degraded", finding.summary, duration_ms)
            return finding

    async def _run_coordinator(
        self,
        context: AgentContext,
        findings: list[AgentFinding],
        publish: ProgressCallback | None,
    ) -> tuple[RiskAssessment, AgentFinding]:
        agent = self._coordinator_agent
        await self._publish(publish, agent.name, "running", "Validating evidence and calculating deterministic risk.")
        started = perf_counter()
        risk, finding = await agent.run(context, findings)
        duration_ms = round((perf_counter() - started) * 1_000)
        finding = finding.model_copy(update={"duration_ms": duration_ms})
        await self._publish(publish, agent.name, "complete", finding.summary, duration_ms)
        return risk, finding

    @staticmethod
    async def _publish(
        callback: ProgressCallback | None,
        agent: str,
        status: str,
        message: str,
        duration_ms: int | None = None,
    ) -> None:
        if callback:
            await callback(
                AgentProgressEvent(
                    agent=agent,
                    status=status,
                    message=message,
                    duration_ms=duration_ms,
                )
            )
