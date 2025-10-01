Directory structure:
└── research_bot/
    ├── README.md
    ├── run_research_workflow.py
    ├── run_worker.py
    ├── agents/
    │   ├── planner_agent.py
    │   ├── research_manager.py
    │   ├── search_agent.py
    │   └── writer_agent.py
    └── workflows/
        └── research_bot_workflow.py


Files Content:

================================================
FILE: openai_agents/research_bot/README.md
================================================
# Research Bot

Multi-agent research system with specialized roles, extended with Temporal's durable execution.

*Adapted from [OpenAI Agents SDK research bot](https://github.com/openai/openai-agents-python/tree/main/examples/research_bot)*

## Architecture

The flow is:

1. User enters their research topic
2. `planner_agent` comes up with a plan to search the web for information. The plan is a list of search queries, with a search term and a reason for each query.
3. For each search item, we run a `search_agent`, which uses the Web Search tool to search for that term and summarize the results. These all run in parallel.
4. Finally, the `writer_agent` receives the search summaries, and creates a written report.

## Running the Example

First, start the worker:
```bash
uv run openai_agents/research_bot/run_worker.py
```

Then run the research workflow:
```bash
uv run openai_agents/research_bot/run_research_workflow.py
```

## Suggested Improvements

If you're building your own research bot, some ideas to add to this are:

1. Retrieval: Add support for fetching relevant information from a vector store. You could use the File Search tool for this.
2. Image and file upload: Allow users to attach PDFs or other files, as baseline context for the research.
3. More planning and thinking: Models often produce better results given more time to think. Improve the planning process to come up with a better plan, and add an evaluation step so that the model can choose to improve its results, search for more stuff, etc.
4. Code execution: Allow running code, which is useful for data analysis.


================================================
FILE: openai_agents/research_bot/run_research_workflow.py
================================================
import asyncio

from temporalio.client import Client
from temporalio.contrib.openai_agents import OpenAIAgentsPlugin

from openai_agents.research_bot.workflows.research_bot_workflow import ResearchWorkflow


async def main():
    # Create client connected to server at the given address
    client = await Client.connect(
        "localhost:7233",
        plugins=[
            OpenAIAgentsPlugin(),
        ],
    )

    # Execute a workflow
    result = await client.execute_workflow(
        ResearchWorkflow.run,
        "Caribbean vacation spots in April, optimizing for surfing, hiking and water sports",
        id="research-workflow",
        task_queue="openai-agents-task-queue",
    )

    print(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(main())



================================================
FILE: openai_agents/research_bot/run_worker.py
================================================
from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio.client import Client
from temporalio.contrib.openai_agents import ModelActivityParameters, OpenAIAgentsPlugin
from temporalio.worker import Worker

from openai_agents.research_bot.workflows.research_bot_workflow import ResearchWorkflow


async def main():
    # Create client connected to server at the given address
    client = await Client.connect(
        "localhost:7233",
        plugins=[
            OpenAIAgentsPlugin(
                model_params=ModelActivityParameters(
                    start_to_close_timeout=timedelta(seconds=120)
                )
            ),
        ],
    )

    worker = Worker(
        client,
        task_queue="openai-agents-task-queue",
        workflows=[
            ResearchWorkflow,
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())



================================================
FILE: openai_agents/research_bot/agents/planner_agent.py
================================================
from agents import Agent
from pydantic import BaseModel

PROMPT = (
    "You are a helpful research assistant. Given a query, come up with a set of web searches "
    "to perform to best answer the query. Output between 5 and 20 terms to query for."
)


class WebSearchItem(BaseModel):
    reason: str
    "Your reasoning for why this search is important to the query."

    query: str
    "The search term to use for the web search."


class WebSearchPlan(BaseModel):
    searches: list[WebSearchItem]
    """A list of web searches to perform to best answer the query."""


def new_planner_agent():
    return Agent(
        name="PlannerAgent",
        instructions=PROMPT,
        model="gpt-4o",
        output_type=WebSearchPlan,
    )



================================================
FILE: openai_agents/research_bot/agents/research_manager.py
================================================
from __future__ import annotations

import asyncio

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    # TODO: Restore progress updates
    from agents import RunConfig, Runner, custom_span, trace

    from openai_agents.research_bot.agents.planner_agent import (
        WebSearchItem,
        WebSearchPlan,
        new_planner_agent,
    )
    from openai_agents.research_bot.agents.search_agent import new_search_agent
    from openai_agents.research_bot.agents.writer_agent import (
        ReportData,
        new_writer_agent,
    )


class ResearchManager:
    def __init__(self):
        self.run_config = RunConfig()
        self.search_agent = new_search_agent()
        self.planner_agent = new_planner_agent()
        self.writer_agent = new_writer_agent()

    async def run(self, query: str) -> str:
        with trace("Research trace"):
            search_plan = await self._plan_searches(query)
            search_results = await self._perform_searches(search_plan)
            report = await self._write_report(query, search_results)

        return report.markdown_report

    async def _plan_searches(self, query: str) -> WebSearchPlan:
        result = await Runner.run(
            self.planner_agent,
            f"Query: {query}",
            run_config=self.run_config,
        )
        return result.final_output_as(WebSearchPlan)

    async def _perform_searches(self, search_plan: WebSearchPlan) -> list[str]:
        with custom_span("Search the web"):
            num_completed = 0
            tasks = [
                asyncio.create_task(self._search(item)) for item in search_plan.searches
            ]
            results = []
            for task in workflow.as_completed(tasks):
                result = await task
                if result is not None:
                    results.append(result)
                num_completed += 1
            return results

    async def _search(self, item: WebSearchItem) -> str | None:
        input = f"Search term: {item.query}\nReason for searching: {item.reason}"
        try:
            result = await Runner.run(
                self.search_agent,
                input,
                run_config=self.run_config,
            )
            return str(result.final_output)
        except Exception:
            return None

    async def _write_report(self, query: str, search_results: list[str]) -> ReportData:
        input = f"Original query: {query}\nSummarized search results: {search_results}"
        result = await Runner.run(
            self.writer_agent,
            input,
            run_config=self.run_config,
        )

        return result.final_output_as(ReportData)



================================================
FILE: openai_agents/research_bot/agents/search_agent.py
================================================
from agents import Agent, WebSearchTool
from agents.model_settings import ModelSettings

INSTRUCTIONS = (
    "You are a research assistant. Given a search term, you search the web for that term and "
    "produce a concise summary of the results. The summary must 2-3 paragraphs and less than 300 "
    "words. Capture the main points. Write succinctly, no need to have complete sentences or good "
    "grammar. This will be consumed by someone synthesizing a report, so its vital you capture the "
    "essence and ignore any fluff. Do not include any additional commentary other than the summary "
    "itself."
)


def new_search_agent():
    return Agent(
        name="Search agent",
        instructions=INSTRUCTIONS,
        tools=[WebSearchTool()],
        model_settings=ModelSettings(tool_choice="required"),
    )



================================================
FILE: openai_agents/research_bot/agents/writer_agent.py
================================================
# Agent used to synthesize a final report from the individual summaries.
from agents import Agent
from pydantic import BaseModel

PROMPT = (
    "You are a senior researcher tasked with writing a cohesive report for a research query. "
    "You will be provided with the original query, and some initial research done by a research "
    "assistant.\n"
    "You should first come up with an outline for the report that describes the structure and "
    "flow of the report. Then, generate the report and return that as your final output.\n"
    "The final output should be in markdown format, and it should be lengthy and detailed. Aim "
    "for 5-10 pages of content, at least 1000 words."
)


class ReportData(BaseModel):
    short_summary: str
    """A short 2-3 sentence summary of the findings."""

    markdown_report: str
    """The final report"""

    follow_up_questions: list[str]
    """Suggested topics to research further"""


def new_writer_agent():
    return Agent(
        name="WriterAgent",
        instructions=PROMPT,
        model="o3-mini",
        output_type=ReportData,
    )



================================================
FILE: openai_agents/research_bot/workflows/research_bot_workflow.py
================================================
from temporalio import workflow

from openai_agents.research_bot.agents.research_manager import ResearchManager


@workflow.defn
class ResearchWorkflow:
    @workflow.run
    async def run(self, query: str) -> str:
        return await ResearchManager().run(query)


