"""
Report Generator

Creates comprehensive research reports:
- Executive summary
- Detailed findings
- Evidence analysis
- Recommendations
- Multiple output formats (Markdown, HTML)
"""

import json
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

from agents import Finding
from api_pool import LLMClient, get_client
import config


@dataclass
class ReportSection:
    """A section of the research report."""
    title: str
    content: str
    subsections: list["ReportSection"] = None


class ReportGenerator:
    """
    Generates comprehensive research reports.

    Features:
    - LLM-powered synthesis
    - Multiple formats (MD, HTML)
    - Structured sections
    - Citation management
    """

    def __init__(self, client: LLMClient = None):
        self.client = client or get_client()

    async def generate_report(
        self,
        research_task: str,
        findings: list[Finding],
        documents: list[str],
        elapsed_hours: float,
        metadata: dict = None,
    ) -> str:
        """
        Generate a comprehensive research report.

        Args:
            research_task: The original research task
            findings: All findings from agents
            documents: List of source documents
            elapsed_hours: Total research time
            metadata: Additional metadata

        Returns:
            Markdown formatted report
        """
        print("[Report] Generating comprehensive report...")

        # Group findings by agent role
        findings_by_role = {}
        for f in findings:
            role = f.agent_role
            if role not in findings_by_role:
                findings_by_role[role] = []
            findings_by_role[role].append(f)

        # Generate sections
        executive_summary = await self._generate_executive_summary(
            research_task, findings
        )
        methodology = self._generate_methodology_section(documents, elapsed_hours)
        detailed_findings = await self._generate_findings_section(findings_by_role)
        synthesis = await self._generate_synthesis(research_task, findings)
        recommendations = await self._generate_recommendations(research_task, findings)
        limitations = self._generate_limitations_section(findings)

        # Build report
        report = self._build_report(
            research_task=research_task,
            executive_summary=executive_summary,
            methodology=methodology,
            detailed_findings=detailed_findings,
            synthesis=synthesis,
            recommendations=recommendations,
            limitations=limitations,
            elapsed_hours=elapsed_hours,
            num_findings=len(findings),
            num_documents=len(documents),
            metadata=metadata,
        )

        return report

    async def _generate_executive_summary(
        self,
        research_task: str,
        findings: list[Finding],
    ) -> str:
        """Generate executive summary using LLM."""
        findings_text = "\n".join([
            f"- [{f.agent_role}] {f.content[:300]}"
            for f in findings[:10]  # Top 10 findings
        ])

        prompt = f"""Based on the following research findings, write an executive summary.

RESEARCH TASK: {research_task}

KEY FINDINGS:
{findings_text}

Write a concise executive summary (3-4 paragraphs) that:
1. States the research objective
2. Highlights the most important findings
3. Identifies key conclusions
4. Notes any critical limitations

Write in professional academic style."""

        try:
            return await self.client.generate(
                prompt=prompt,
                system_instruction="You are a scientific report writer. Be concise and precise.",
            )
        except Exception as e:
            return f"Executive summary generation failed: {e}"

    def _generate_methodology_section(
        self,
        documents: list[str],
        elapsed_hours: float,
    ) -> str:
        """Generate methodology section."""
        return f"""### Research Methodology

**Approach**: Multi-agent systematic review using AI-assisted analysis

**Data Sources**:
- {len(documents)} documents analyzed
- Sources include: {', '.join(documents[:5])}{'...' if len(documents) > 5 else ''}

**Analysis Framework**:
- Literature review by specialized agent
- Data analysis by quantitative expert
- Methodology evaluation by methods expert
- Critical review for bias and gaps
- Synthesis of findings across all perspectives

**Duration**: {elapsed_hours:.1f} hours of automated research

**Tools Used**:
- Google Gemini for analysis
- Multiple specialized research agents
- Automated finding extraction and synthesis
"""

    async def _generate_findings_section(
        self,
        findings_by_role: dict[str, list[Finding]],
    ) -> str:
        """Generate detailed findings section."""
        sections = []

        for role, findings in findings_by_role.items():
            section = f"#### {role}\n\n"

            for i, f in enumerate(findings, 1):
                confidence_badge = {
                    f.confidence >= 0.8: "🟢 High",
                    0.5 <= f.confidence < 0.8: "🟡 Medium",
                    f.confidence < 0.5: "🔴 Low",
                }.get(True, "⚪ Unknown")

                section += f"**Finding {i}** (Confidence: {confidence_badge})\n\n"
                section += f"{f.content}\n\n"

            sections.append(section)

        return "\n".join(sections)

    async def _generate_synthesis(
        self,
        research_task: str,
        findings: list[Finding],
    ) -> str:
        """Generate synthesis section using LLM."""
        findings_text = "\n".join([
            f"- {f.content[:400]}" for f in findings
        ])

        prompt = f"""Synthesize the following research findings into a coherent analysis.

RESEARCH TASK: {research_task}

FINDINGS:
{findings_text}

Provide a synthesis that:
1. Identifies common themes across findings
2. Resolves any contradictions
3. Builds a comprehensive understanding
4. Highlights areas of consensus and disagreement

Write 4-5 paragraphs."""

        try:
            return await self.client.generate(
                prompt=prompt,
                system_instruction="You are a research synthesizer. Combine findings logically.",
            )
        except Exception as e:
            return f"Synthesis generation failed: {e}"

    async def _generate_recommendations(
        self,
        research_task: str,
        findings: list[Finding],
    ) -> str:
        """Generate recommendations using LLM."""
        high_confidence = [f for f in findings if f.confidence >= 0.7]

        findings_text = "\n".join([
            f"- {f.content[:300]}" for f in high_confidence[:8]
        ])

        prompt = f"""Based on the research findings below, provide actionable recommendations.

RESEARCH TASK: {research_task}

HIGH-CONFIDENCE FINDINGS:
{findings_text}

Provide 5-7 specific, actionable recommendations that:
1. Are supported by the evidence
2. Address the research question
3. Consider practical implementation
4. Note any conditions or caveats

Format as a numbered list."""

        try:
            return await self.client.generate(
                prompt=prompt,
                system_instruction="You are a research advisor. Provide practical recommendations.",
            )
        except Exception as e:
            return f"Recommendations generation failed: {e}"

    def _generate_limitations_section(self, findings: list[Finding]) -> str:
        """Generate limitations section."""
        low_confidence = [f for f in findings if f.confidence < 0.5]
        error_findings = [f for f in findings if "error" in f.tags]

        return f"""### Limitations

**Confidence Levels**:
- High confidence findings: {sum(1 for f in findings if f.confidence >= 0.8)}
- Medium confidence findings: {sum(1 for f in findings if 0.5 <= f.confidence < 0.8)}
- Low confidence findings: {len(low_confidence)}

**Known Limitations**:
1. Analysis limited to provided documents
2. AI-generated synthesis may have biases
3. Quantitative data extraction may be incomplete
4. Time constraints may affect depth of analysis

**Errors Encountered**: {len(error_findings)}

**Recommendations for Further Research**:
- Manual validation of key findings
- Additional primary source review
- Expert consultation for domain-specific claims
"""

    def _build_report(
        self,
        research_task: str,
        executive_summary: str,
        methodology: str,
        detailed_findings: str,
        synthesis: str,
        recommendations: str,
        limitations: str,
        elapsed_hours: float,
        num_findings: int,
        num_documents: int,
        metadata: dict = None,
    ) -> str:
        """Build the complete report."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        report = f"""# Research Report

## {research_task}

**Generated**: {timestamp}
**Duration**: {elapsed_hours:.1f} hours
**Findings**: {num_findings}
**Documents Analyzed**: {num_documents}

---

## Executive Summary

{executive_summary}

---

## Methodology

{methodology}

---

## Detailed Findings

{detailed_findings}

---

## Synthesis

{synthesis}

---

## Recommendations

{recommendations}

---

## Limitations and Caveats

{limitations}

---

## Appendix

### Research Configuration
- Model: {config.MODEL_NAME}
- Max agents: {config.MAX_AGENTS}
- Checkpoint interval: {config.CHECKPOINT_INTERVAL_MINUTES} minutes

### Metadata
```json
{json.dumps(metadata or {}, indent=2)}
```

---

*This report was generated automatically using the Research World multi-agent system.*
*Findings should be validated by domain experts before use in decision-making.*
"""
        return report

    def save_report(
        self,
        report: str,
        research_task: str,
        format: str = "md",
    ) -> Path:
        """Save report to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_task = "".join(c if c.isalnum() else "_" for c in research_task[:30])

        filename = f"report_{safe_task}_{timestamp}.{format}"
        filepath = config.REPORTS_DIR / filename

        with open(filepath, "w") as f:
            f.write(report)

        print(f"[Report] Saved to: {filepath}")
        return filepath
