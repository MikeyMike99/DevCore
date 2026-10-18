[//]: # (DOC_ID: SIRA-DEV-CREWAI_README_CLN | VERSION: v1.3 | SCOPE: DEV)

Homepage
  ·
  Open Source
  ·
  Docs
  ·
  Start Cloud Trial
  ·
  Blog
  ·
  Forum

  
    
  
  
    
  
  
    
  
  
    
  
  
    
  

  
    
  
  
    
  
  
    
  

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-1)
### Fast and Flexible Multi-Agent Automation Framework
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-1)

> CrewAI is an open-source Python framework with high-level abstractions and low-level APIs for building production-ready multi-agent workflows.
> It gives developers autonomous agent collaboration through Crews and precise, event-driven control through Flows.

- **CrewAI Crews**: Optimize for autonomy and collaborative intelligence with role-based AI agents.
- **CrewAI Flows**: Build event-driven automations that combine precise workflow control, single LLM calls, and native support for Crews.

With over 100,000 developers certified through our community courses at learn.crewai.com, CrewAI is rapidly becoming the
standard for production-ready agentic automation.

# CrewAI AMP Suite

For organizations that need a commercial control plane around CrewAI, CrewAI AMP Suite adds managed deployment, observability, governance, security, and enterprise support.

You can try one part of the suite, the Crew Control Plane, for free.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-2)
## Crew Control Plane Key Features:
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-2)

- **Tracing & Observability**: Monitor and track your AI agents and workflows in real-time, including metrics, logs, and traces.
- **Unified Control Plane**: A centralized platform for managing, monitoring, and scaling your AI agents and workflows.
- **Seamless Integrations**: Easily connect with existing enterprise systems, data sources, and cloud infrastructure.
- **Advanced Security**: Built-in robust security and compliance measures ensuring safe deployment and management.
- **Actionable Insights**: Real-time analytics and reporting to optimize performance and decision-making.
- **24/7 Support**: Dedicated enterprise support to ensure uninterrupted operation and quick resolution of issues.
- **On-premise and Cloud Deployment Options**: Deploy CrewAI AMP on-premise or in the cloud, depending on your security and compliance requirements.

CrewAI AMP is designed for enterprises seeking a powerful, reliable solution to transform complex business processes into efficient,
intelligent automations.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-3)
## Table of contents
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-3)

- Build with AI
- Why CrewAI?
- Getting Started
  - Learning Resources
  - Understanding Flows and Crews
  - Installation
  - Setting Up Your Crew
  - Running Your Crew
- Key Features
- Examples
  - Quick Tutorial
  - Write Job Descriptions
  - Trip Planner
  - Stock Analysis
  - Using Crews and Flows Together
- Connecting Your Crew to a Model
- When to Use CrewAI
- Contribution
- Telemetry
- License
- Frequently Asked Questions (FAQ)

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-4)
## Build with AI
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-4)

Using an AI coding agent? Teach it CrewAI best practices in one command:

**Claude Code:**
```shell
/plugin marketplace add crewAIInc/skills
/plugin install crewai-skills@crewai-plugins
/reload-plugins
```
Four skills that activate automatically when you ask relevant CrewAI questions:

| Skill | When it runs |
|-------|--------------|
| `getting-started` | Scaffolding new projects, choosing between `LLM.call()` / `Agent` / `Crew` / `Flow`, wiring `crew.jsonc` / `Core Component` |
| `design-agent` | Configuring agents — role, goal, backstory, tools, LLMs, memory, guardrails |
| `design-task` | Writing task descriptions, dependencies, structured output (`output_pydantic`, `output_json`), human review |
| `ask-docs` | Querying the live CrewAI docs MCP server for up-to-date API details |

**Cursor, Codex, Windsurf, and others (skills.sh):**
```shell
npx skills add crewaiinc/skills
```

This installs the official CrewAI Skills — structured instructions that teach coding agents how to scaffold Flows, configure Crews, design agents and tasks, and follow CrewAI patterns.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-5)
## Why CrewAI?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-5)

  

CrewAI unlocks the true potential of multi-agent automation, delivering speed, flexibility, and control through Crews of AI agents and event-driven Flows:

- **Purpose-built architecture**: Designed specifically for agent orchestration, with a lightweight Python core and clean primitives for real-world automation.
- **High Performance**: Optimized for speed and minimal resource usage, enabling faster execution.
- **Flexible Low-Level Customization**: Complete freedom to customize everything from workflows and system architecture to agent behaviors, internal prompts, and execution logic.
- **Ideal for Every Use Case**: Proven effective for simple tasks, complex workflows, and production-grade automation.
- **Robust Community**: Backed by a rapidly growing community of over **100,000 certified** developers offering comprehensive support and resources.

CrewAI empowers developers and teams to build intelligent automations that balance simplicity, flexibility, and production-grade control.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-6)
## Getting Started
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-6)

Setup and run your first CrewAI agents by following this tutorial.

[](https://www.youtube.com/watch?v=-kSOTtYzgEw "CrewAI Getting Started Tutorial")

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-7)
### Learning Resources
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-7)

Learn CrewAI through our comprehensive courses:

- Multi AI Agent Systems with CrewAI - Master the fundamentals of multi-agent systems
- Practical Multi AI Agents and Advanced Use Cases - Deep dive into advanced implementations

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-8)
### Understanding Flows and Crews
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-8)

CrewAI offers two powerful, complementary approaches that work seamlessly together to build sophisticated AI applications:

1. **Crews**: Teams of AI agents with true autonomy and agency, working together to accomplish complex tasks through role-based collaboration. Crews enable:

   - Natural, autonomous decision-making between agents
   - Dynamic task delegation and collaboration
   - Specialized roles with defined goals and expertise
   - Flexible problem-solving approaches

2. **Flows**: Production-ready, event-driven workflows that deliver precise control over complex automations. Flows provide:

   - Fine-grained control over execution paths for real-world scenarios
   - Secure, consistent state management between tasks
   - Clean integration of AI agents with production Python code
   - Conditional branching for complex business logic

The true power of CrewAI emerges when combining Crews and Flows. This synergy allows you to:

- Build complex, production-grade applications
- Balance autonomy with precise control
- Handle sophisticated real-world scenarios
- Maintain clean, maintainable code structure

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-9)
### Getting Started with Installation
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-9)

To get started with CrewAI, follow these simple steps. The full walkthrough lives in the installation guide.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-1)
### 1. Installation
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-1)

CrewAI requires `Python >=3.10 and 
```

This command creates a new project folder with the following structure:

```
my_project/
├── .gitignore
├── .env
├── agents/
│   └── researcher.jsonc
├── crew.jsonc
├── knowledge/
├── pyproject.toml
├── README.md
├── skills/
└── tools/
```

If you need the older Python/YAML scaffold with `Core Component`, `config/agents.yaml`, and `config/tasks.yaml`, run:

```shell
crewai create crew  --classic
```

See Using Annotations for the classic pattern.

#### To customize your project, you can:

- Modify `agents/*.jsonc` to define each agent's role, goal, backstory, LLM, tools, and behavior.
- Modify `crew.jsonc` to define tasks, process, and input defaults.
- Add custom tools in `tools/` and reference them as `"custom:"`.
- Add optional knowledge files in `knowledge/` and skill files in `skills/`.
- Add your environment variables into the `.env` file.

Use `{placeholder}` values in agent and task text, then set defaults in `crew.jsonc` under `inputs`. When you run `crewai run`, the CLI prompts for any missing values.

#### Example of a simple crew with a sequential process:

```shell
crewai create crew latest-ai-development
cd latest_ai_development
```

Then edit the generated files:

**agents/researcher.jsonc**

```jsonc
{
  "role": "{topic} Senior Data Researcher",
  "goal": "Uncover cutting-edge developments in {topic}",
  "backstory": "You're a seasoned researcher who finds relevant information and presents it clearly.",
  "llm": "openai/gpt-4o",
  "tools": ["SerperDevTool"],
  "settings": {
    "verbose": true
  }
}
```

**agents/reporting_analyst.jsonc**

```jsonc
{
  "role": "{topic} Reporting Analyst",
  "goal": "Create detailed reports based on {topic} data analysis and research findings",
  "backstory": "You're a meticulous analyst who turns complex data into clear, concise reports.",
  "llm": "openai/gpt-4o",
  "settings": {
    "verbose": true
  }
}
```

**crew.jsonc**

```jsonc
{
  "name": "Latest AI Development",
  "agents": ["researcher", "reporting_analyst"],
  "tasks": [
    {
      "name": "research_task",
      "description": "Conduct thorough research about {topic}. Find recent, relevant information.",
      "expected_output": "A list with 10 bullet points of the most relevant information about {topic}.",
      "agent": "researcher"
    },
    {
      "name": "reporting_task",
      "description": "Review the research and expand each topic into a full section for a report.",
      "expected_output": "A markdown report with the main topics, each with a full section of information. No fenced code blocks around the whole document.",
      "agent": "reporting_analyst",
      "context": ["research_task"],
      "output_file": "output/report.md",
      "markdown": true
    }
  ],
  "process": "sequential",
  "verbose": true,
  "inputs": {
    "topic": "AI Agents"
  }
}
```

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-3)
### 3. Running Your Crew
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-3)

Before running your crew, set the required keys in your `.env` file:

- Your model provider API key — see LLM setup
- A Serper.dev API key if you use web search: `SERPER_API_KEY=YOUR_KEY_HERE`

Then install dependencies and run from the project directory:

```shell
crewai install
crewai run
```

If you need additional packages, use `uv add `.

You should see the output in the console, and `output/report.md` should be created in the project root.

In addition to the sequential process, you can use the hierarchical process, which automatically assigns a manager to the defined crew to properly coordinate the planning and execution of tasks through delegation and validation of results. See more about the processes here.

For a Flow-first walkthrough, see the Quickstart.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-10)
## Key Features
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-10)

CrewAI gives developers a practical foundation for building agentic systems that move from prototype to production: autonomous collaboration where it helps, explicit workflow control where it matters, and Python-native customization throughout.

- **Crews for autonomy**: Model teams of specialized AI agents with roles, goals, tools, and tasks.
- **Flows for control**: Build event-driven workflows with state, branching, routing, and production logic.
- **Seamless integration**: Combine Crews and Flows to create complex, real-world automations.
- **Python-native customization**: Customize prompts, tools, execution paths, state, and integrations without fighting the framework.
- **Agent-ready capabilities**: Use tools, memory, knowledge, checkpointing, async execution, and MCP/A2A support for more capable production agents.
- **Production-ready patterns**: Add deterministic steps, human input, structured outputs, and checkpointing as your system grows.
- **Thriving community**: Backed by robust documentation and over 100,000 certified developers, providing exceptional support and guidance.

Choose CrewAI to build powerful, adaptable, and production-ready AI automations.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-11)
## Examples
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-11)

You can test different real life examples of AI crews in the CrewAI-examples repo:

- Landing Page Generator
- Having Human input on the execution
- Trip Planner
- Stock Analysis

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-12)
### Quick Tutorial
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-12)

[](https://www.youtube.com/watch?v=tnejrr-0a94 "CrewAI Tutorial")

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-13)
### Write Job Descriptions
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-13)

Check out code for this example or watch a video below:

[](https://www.youtube.com/watch?v=u98wEMz-9to "Jobs postings")

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-14)
### Trip Planner
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-14)

Check out code for this example or watch a video below:

[](https://www.youtube.com/watch?v=xis7rWp-hjs "Trip Planner")

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-15)
### Stock Analysis
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-15)

Check out code for this example or watch a video below:

[](https://www.youtube.com/watch?v=e0Uj4yWdaAg "Stock Analysis")

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-16)
### Using Crews and Flows Together
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-16)

CrewAI's power truly shines when combining Crews with Flows to create sophisticated automation pipelines.
CrewAI flows support logical operators like `or_` and `and_` to combine multiple conditions. This can be used with `@start`, `@listen`, or `@router` decorators to create complex triggering conditions.

- `or_`: Triggers when any of the specified conditions are met.
- `and_`: Triggers when all of the specified conditions are met.

Here's how you can orchestrate multiple Crews within a Flow:

```python
from crewai.flow.flow import Flow, listen, start, router, or_
from crewai import Crew, Agent, Task, Process
from pydantic import BaseModel

# Define structured state for precise control
class MarketState(BaseModel):
    sentiment: str = "neutral"
    confidence: float = 0.0
    recommendations: list = []

class AdvancedAnalysisFlow(Flow[MarketState]):
    @start()
    def fetch_market_data(self):
        # Demonstrate low-level control with structured state
        self.state.sentiment = "analyzing"
        return {"sector": "tech", "timeframe": "1W"}  # These parameters match the task description template

    @listen(fetch_market_data)
    def analyze_with_crew(self, market_data):
        # Show crew agency through specialized roles
        analyst = Agent(
            role="Senior Market Analyst",
            goal="Conduct deep market analysis with expert insight",
            backstory="You're a veteran analyst known for identifying subtle market patterns"
        )
        researcher = Agent(
            role="Data Researcher",
            goal="Gather and validate supporting market data",
            backstory="You excel at finding and correlating multiple data sources"
        )

        analysis_task = Task(
            description="Analyze {sector} sector data for the past {timeframe}",
            expected_output="Detailed market analysis with confidence score",
            agent=analyst
        )
        research_task = Task(
            description="Find supporting data to validate the analysis",
            expected_output="Corroborating evidence and potential contradictions",
            agent=researcher
        )

        # Demonstrate crew autonomy
        analysis_crew = Crew(
            agents=[analyst, researcher],
            tasks=[analysis_task, research_task],
            process=Process.sequential,
            verbose=True
        )
        return analysis_crew.kickoff(inputs=market_data)  # Pass market_data as named inputs

    @router(analyze_with_crew)
    def determine_next_steps(self):
        # Show flow control with conditional routing
        if self.state.confidence > 0.8:
            return "high_confidence"
        elif self.state.confidence > 0.5:
            return "medium_confidence"
        return "low_confidence"

    @listen("high_confidence")
    def execute_strategy(self):
        # Demonstrate complex decision making
        strategy_crew = Crew(
            agents=[
                Agent(role="Strategy Expert",
                      goal="Develop optimal market strategy")
            ],
            tasks=[
                Task(description="Create detailed strategy based on analysis",
                     expected_output="Step-by-step action plan")
            ]
        )
        return strategy_crew.kickoff()

    @listen(or_("medium_confidence", "low_confidence"))
    def request_additional_analysis(self):
        self.state.recommendations.append("Gather more data")
        return "Additional analysis required"
```

This example demonstrates how to:

1. Use Python code for basic data operations
2. Create and execute Crews as steps in your workflow
3. Use Flow decorators to manage the sequence of operations
4. Implement conditional branching based on Crew results

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-17)
## Connecting Your Crew to a Model
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-17)

CrewAI supports using various LLMs through a variety of connection options. By default your agents will use the OpenAI API when querying the model. However, there are several other ways to allow your agents to connect to models. For example, you can configure your agents to use a local model via the Ollama tool.

Please refer to the Connect CrewAI to LLMs page for details on configuring your agents' connections to models.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-18)
## When to Use CrewAI
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-18)

Use CrewAI when you need more than a single prompt or chatbot: multi-step work, specialized agents, tool use, structured outputs, human review, or workflows that combine autonomous reasoning with explicit business logic.

CrewAI is especially useful when you want to:

- Coordinate multiple agents with clear roles and tasks.
- Wrap agent work in deterministic, event-driven workflows.
- Keep application logic in regular Python.
- Move from experiment to production without changing frameworks.
- Add tools, memory, checkpointing, and async execution as your system grows.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-19)
## Contribution
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-19)

CrewAI is open-source and we welcome contributions. See
`.github/CONTRIBUTING.md` for the full setup guide,
branching conventions, and PR checklist.

Quick start:

```bash
git clone https://github.com/crewAIInc/crewAI.git
cd crewAI
uv sync --all-groups --all-extras
uv run pre-commit install
```

```bash
# Tests
uv run pytest lib/crewai/tests/ -x -q

# Type checks
uv run mypy lib/
```

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-20)
### Contributing to the docs
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-20)

The site at docs.crewai.com is published from
`docs/` by Mintlify. The docs use directory-based
versioning: edits to `docs/edge//...` (e.g.
`docs/edge/en/concepts/agents.mdx`) land under the **Edge** version selector
immediately and are frozen into a new versioned snapshot under
`docs/v/` at the next release cut. Frozen snapshots are immutable — CI
rejects PRs that modify them without a `[docs-freeze]` title prefix. The
release CLI (`devtools release`) handles the freeze automatically; see
`.github/CONTRIBUTING.md` for contributor guidance and
`lib/devtools/README.md` for release tooling.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-21)
## Telemetry
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-21)

CrewAI uses anonymous telemetry to collect usage data with the main purpose of helping us improve the library by focusing our efforts on the most used features, integrations and tools.

It's pivotal to understand that **NO data is collected** concerning prompts, task descriptions, agents' backstories or goals, usage of tools, API calls, responses, any data processed by the agents, or secrets and environment variables, with the exception of the conditions mentioned. When the `share_crew` feature is enabled, detailed data including task descriptions, agents' backstories or goals, and other specific attributes are collected to provide deeper insights while respecting user privacy. Users can disable telemetry by setting the environment variable OTEL_SDK_DISABLED to true.

Data collected includes:

- Version of CrewAI
  - So we can understand how many users are using the latest version
- Version of Python
  - So we can decide on what versions to better support
- General OS (e.g. number of CPUs, macOS/Windows/Linux)
  - So we know what OS we should focus on and if we could build specific OS related features
- Number of agents and tasks in a crew
  - So we make sure we are testing internally with similar use cases and educate people on the best practices
- Crew Process being used
  - Understand where we should focus our efforts
- If Agents are using memory or allowing delegation
  - Understand if we improved the features or maybe even drop them
- If Tasks are being executed in parallel or sequentially
  - Understand if we should focus more on parallel execution
- Language model being used
  - Improved support on most used languages
- Roles of agents in a crew
  - Understand high level use cases so we can build better tools, integrations and examples about it
- Tools names available
  - Understand out of the publicly available tools, which ones are being used the most so we can improve them

Users can opt-in to Further Telemetry, sharing the complete telemetry data by setting the `share_crew` attribute to `True` on their Crews. Enabling `share_crew` results in the collection of detailed crew and task execution data, including `goal`, `backstory`, `context`, and `output` of tasks. This enables a deeper insight into usage patterns while respecting the user's choice to share.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-22)
## License
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-22)

CrewAI is released under the MIT License.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-23)
## Frequently Asked Questions (FAQ)
[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-24)

### General
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-24)

- What exactly is CrewAI?
- How do I install CrewAI?
- Is CrewAI a standalone framework?
- Is CrewAI open-source?
- Does CrewAI collect data from users?

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-25)
### Features and Capabilities
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-25)

- Can CrewAI handle complex use cases?
- Can I use CrewAI with local AI models?
- What makes Crews different from Flows?
- Does CrewAI support fine-tuning or training custom models?

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-26)
### Resources and Community
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-26)

- Where can I find real-world CrewAI examples?
- How can I contribute to CrewAI?

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-27)
### Enterprise Features
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-27)

- What additional features does CrewAI AMP offer?
- Is CrewAI AMP available for cloud and on-premise deployments?
- Can I try CrewAI AMP for free?

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-28)
### Q: What exactly is CrewAI?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-28)

A: CrewAI is a lean, fast Python framework built specifically for orchestrating autonomous AI agents and production-ready agentic workflows.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-29)
### Q: How do I install CrewAI?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-29)

A: Install the CrewAI CLI with UV:

```shell
uv tool install crewai
```

Then create a project with `crewai create crew `, run `crewai install`, and start it with `crewai run`. See the installation guide for details.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-30)
### Q: Is CrewAI a standalone framework?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-30)

A: Yes. CrewAI is a standalone Python framework with its own primitives for agents, tasks, crews, flows, tools, and orchestration.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-31)
### Q: Can CrewAI handle complex use cases?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-31)

A: Yes. CrewAI excels at both simple and highly complex real-world scenarios, offering deep customization options at both high and low levels, from internal prompts to sophisticated workflow orchestration.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-32)
### Q: Can I use CrewAI with local AI models?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-32)

A: Absolutely! CrewAI supports various language models, including local ones. Tools like Ollama and LM Studio allow seamless integration. Check the LLM Connections documentation for more details.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-33)
### Q: What makes Crews different from Flows?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-33)

A: Crews provide autonomous agent collaboration, ideal for tasks requiring flexible decision-making and dynamic interaction. Flows offer precise, event-driven control, ideal for managing detailed execution paths and secure state management. You can seamlessly combine both for maximum effectiveness.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-34)
### Q: Is CrewAI open-source?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-34)

A: Yes, CrewAI is open-source and actively encourages community contributions and collaboration.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-35)
### Q: Does CrewAI collect data from users?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-35)

A: CrewAI collects anonymous telemetry data strictly for improvement purposes. Sensitive data such as prompts, tasks, or API responses are never collected unless explicitly enabled by the user.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-36)
### Q: Where can I find real-world CrewAI examples?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-36)

A: Check out practical examples in the CrewAI-examples repository, covering use cases like trip planners, stock analysis, and job postings.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-37)
### Q: How can I contribute to CrewAI?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-37)

A: Contributions are warmly welcomed! Fork the repository, create your branch, implement your changes, and submit a pull request. See `.github/CONTRIBUTING.md` for detailed guidelines.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-38)
### Q: What additional features does CrewAI AMP offer?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-38)

A: CrewAI AMP provides advanced features such as a unified control plane, real-time observability, secure integrations, advanced security, actionable insights, and dedicated 24/7 enterprise support.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-39)
### Q: Is CrewAI AMP available for cloud and on-premise deployments?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-39)

A: Yes, CrewAI AMP supports both cloud-based and on-premise deployment options, allowing enterprises to meet their specific security and compliance requirements.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-40)
### Q: Can I try CrewAI AMP for free?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-40)

A: Yes, you can explore part of the CrewAI AMP Suite by accessing the Crew Control Plane for free.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-41)
### Q: Does CrewAI support fine-tuning or training custom models?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-41)

A: Yes, CrewAI can integrate with custom-trained or fine-tuned models, allowing you to enhance your agents with domain-specific knowledge and accuracy.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-42)
### Q: Can CrewAI agents interact with external tools and APIs?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-42)

A: Absolutely! CrewAI agents can easily integrate with external tools, APIs, and databases, empowering them to leverage real-world data and resources.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-43)
### Q: Is CrewAI suitable for production environments?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-43)

A: Yes, CrewAI is designed with production-grade patterns that support reliable, stable, and scalable agentic workflows.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-44)
### Q: How scalable is CrewAI?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-44)

A: CrewAI is highly scalable, supporting simple automations and large-scale workflows involving numerous agents and complex tasks simultaneously.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-45)
### Q: Does CrewAI offer debugging and monitoring tools?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-45)

A: Yes, CrewAI AMP includes advanced debugging, tracing, and real-time observability features, simplifying the management and troubleshooting of your automations.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-46)
### Q: What programming languages does CrewAI support?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-46)

A: CrewAI is primarily Python-based but easily integrates with services and APIs written in any programming language through its flexible API integration capabilities.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-47)
### Q: Does CrewAI offer educational resources for beginners?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-47)

A: Yes, CrewAI provides extensive beginner-friendly tutorials, courses, and documentation through learn.crewai.com, supporting developers at all skill levels.

[//]: # (SECTION_ID: SIRA-DEV-CREWAI_README_CLN-SEC-48)
### Q: Can CrewAI automate human-in-the-loop workflows?
[//]: # (SECTION_ID: SIRA-DOC-CREWAI_README_-SEC-48)

A: Yes, CrewAI fully supports human-in-the-loop workflows, allowing seamless collaboration between human experts and AI agents for enhanced decision-making.
