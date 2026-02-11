"""
Research Agents

Specialized agents for long-running research tasks:
- Literature Reviewer
- Data Analyst
- Methodology Expert
- Synthesizer
- Critic
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from enum import Enum

from api_pool import LLMClient, get_client
from pdf_processor import ProcessedDocument
import config


class AgentStatus(Enum):
    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Finding:
    """A research finding from an agent."""
    agent_id: str
    agent_role: str
    timestamp: datetime
    content: str
    sources: list[str]
    confidence: float
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "agent_role": self.agent_role,
            "timestamp": self.timestamp.isoformat(),
            "content": self.content,
            "sources": self.sources,
            "confidence": self.confidence,
            "tags": self.tags,
        }


@dataclass
class AgentState:
    """State of a research agent."""
    agent_id: str
    role: str
    status: AgentStatus = AgentStatus.IDLE
    current_task: str = ""
    findings: list[Finding] = field(default_factory=list)
    tasks_completed: int = 0
    errors: int = 0
    last_active: datetime = None

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "status": self.status.value,
            "current_task": self.current_task,
            "findings": [f.to_dict() for f in self.findings],
            "tasks_completed": self.tasks_completed,
            "errors": self.errors,
            "last_active": self.last_active.isoformat() if self.last_active else None,
        }


class ResearchAgent:
    """
    Base class for research agents.

    Each agent:
    - Has a specific role and expertise
    - Works on assigned tasks
    - Produces findings
    - Can collaborate with other agents
    """

    def __init__(
        self,
        agent_id: str,
        role: str,
        description: str,
        client: LLMClient = None,
    ):
        self.agent_id = agent_id
        self.role = role
        self.description = description
        self.client = client or get_client()
        self.state = AgentState(agent_id=agent_id, role=role)

        # System instruction for this agent
        self.system_instruction = f"""You are a research agent specialized in: {role}

Your expertise: {description}

Guidelines:
1. Be thorough and analytical
2. Cite sources when possible
3. Express confidence levels (high/medium/low)
4. Identify gaps and uncertainties
5. Provide actionable insights

Format your responses as JSON with this structure:
{{
    "key_findings": ["finding 1", "finding 2", ...],
    "evidence": ["evidence 1", "evidence 2", ...],
    "confidence": "high/medium/low",
    "gaps": ["gap 1", "gap 2", ...],
    "recommendations": ["rec 1", "rec 2", ...]
}}"""

    async def research(
        self,
        task: str,
        context: str = "",
        previous_findings: list[Finding] = None,
    ) -> Finding:
        """
        Conduct research on a specific task.

        Args:
            task: The research task to perform
            context: Relevant context (from documents)
            previous_findings: Findings from other agents

        Returns:
            A Finding object with results
        """
        self.state.status = AgentStatus.WORKING
        self.state.current_task = task
        self.state.last_active = datetime.now()

        # Build prompt
        prompt = self._build_prompt(task, context, previous_findings)

        try:
            # Call LLM
            response = await self.client.generate(
                prompt=prompt,
                system_instruction=self.system_instruction,
            )

            # Parse response
            finding = self._parse_response(response, task)
            self.state.findings.append(finding)
            self.state.tasks_completed += 1
            self.state.status = AgentStatus.IDLE

            return finding

        except Exception as e:
            self.state.errors += 1
            self.state.status = AgentStatus.FAILED
            print(f"[{self.agent_id}] Error: {e}")

            # Return partial finding on error
            return Finding(
                agent_id=self.agent_id,
                agent_role=self.role,
                timestamp=datetime.now(),
                content=f"Error during research: {str(e)}",
                sources=[],
                confidence=0.0,
                tags=["error"],
            )

    def _build_prompt(
        self,
        task: str,
        context: str,
        previous_findings: list[Finding],
    ) -> str:
        """Build the research prompt."""
        parts = [f"RESEARCH TASK:\n{task}"]

        if context:
            parts.append(f"\nRELEVANT DOCUMENTS:\n{context[:8000]}")  # Limit context

        if previous_findings:
            findings_text = "\n".join([
                f"- [{f.agent_role}] {f.content[:500]}"
                for f in previous_findings[-5:]  # Last 5 findings
            ])
            parts.append(f"\nPREVIOUS FINDINGS FROM TEAM:\n{findings_text}")

        parts.append("\nProvide your analysis:")

        return "\n".join(parts)

    def _parse_response(self, response: str, task: str) -> Finding:
        """Parse LLM response into a Finding."""
        confidence = 0.5

        # Try to parse JSON
        try:
            # Extract JSON if wrapped in markdown
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]

            data = json.loads(response)
            key_findings = data.get("key_findings", [])
            content = "\n".join(key_findings) if key_findings else response

            conf_str = data.get("confidence", "medium")
            confidence = {"high": 0.9, "medium": 0.6, "low": 0.3}.get(conf_str, 0.5)

            tags = data.get("tags", [])

        except json.JSONDecodeError:
            content = response
            tags = []

        return Finding(
            agent_id=self.agent_id,
            agent_role=self.role,
            timestamp=datetime.now(),
            content=content,
            sources=[],
            confidence=confidence,
            tags=tags,
        )

    def get_status(self) -> dict:
        """Get current agent status."""
        return self.state.to_dict()


class LiteratureReviewer(ResearchAgent):
    """Agent specialized in reviewing scientific literature."""

    def __init__(self, agent_id: str = "lit_reviewer"):
        super().__init__(
            agent_id=agent_id,
            role="Literature Reviewer",
            description="""Expert at reviewing scientific papers, identifying key findings,
evaluating study quality, and synthesizing evidence across multiple publications.
Focus on: study design, sample sizes, statistical significance, and clinical relevance.""",
        )


class DataAnalyst(ResearchAgent):
    """Agent specialized in data analysis."""

    def __init__(self, agent_id: str = "data_analyst"):
        super().__init__(
            agent_id=agent_id,
            role="Data Analyst",
            description="""Expert at analyzing quantitative data, statistics, and numerical results.
Focus on: effect sizes, confidence intervals, p-values, clinical significance vs statistical significance,
data quality, and appropriate statistical methods.""",
        )


class MethodologyExpert(ResearchAgent):
    """Agent specialized in research methodology."""

    def __init__(self, agent_id: str = "methodology"):
        super().__init__(
            agent_id=agent_id,
            role="Methodology Expert",
            description="""Expert at evaluating research methods and experimental design.
Focus on: study design (RCT, observational, etc.), bias assessment, confounding factors,
generalizability, and internal/external validity.""",
        )


class Synthesizer(ResearchAgent):
    """Agent specialized in synthesizing findings."""

    def __init__(self, agent_id: str = "synthesizer"):
        super().__init__(
            agent_id=agent_id,
            role="Research Synthesizer",
            description="""Expert at combining findings from multiple sources into coherent insights.
Focus on: identifying themes, resolving contradictions, building comprehensive understanding,
and creating actionable conclusions.""",
        )


class Critic(ResearchAgent):
    """Agent specialized in critical analysis."""

    def __init__(self, agent_id: str = "critic"):
        super().__init__(
            agent_id=agent_id,
            role="Critical Analyst",
            description="""Expert at identifying gaps, limitations, and counter-arguments.
Focus on: weaknesses in evidence, alternative explanations, missing perspectives,
potential biases, and areas needing more research.""",
        )


def create_research_team() -> dict[str, ResearchAgent]:
    """Create a full research team."""
    return {
        "literature_reviewer": LiteratureReviewer(),
        "data_analyst": DataAnalyst(),
        "methodology_expert": MethodologyExpert(),
        "synthesizer": Synthesizer(),
        "critic": Critic(),
    }
