# 🤖 Enterprise HR AI Copilot v2.0 (`v2-HR-copilot`)

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.48+-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL%20%26%20PGVector-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com)
[![Groq](https://img.shields.io/badge/Groq-LPU%20Ultra--Fast%20Inference-F05032?style=for-the-badge&logo=fastapi&logoColor=white)](https://groq.com)
[![Architecture](https://img.shields.io/badge/Architecture-Multi--Agent%20DAG%20%26%20CQRS-1A365D?style=for-the-badge)](https://github.com/JEEVANPRANAVRAVIKUMAR/v2-HR-copilot)
[![QA Benchmark](https://img.shields.io/badge/QA%20Benchmark-100%25%20Passed%20(100%2F100)-22C55E?style=for-the-badge)](#-senior-qa-benchmark-suite-100-pass-rate)
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)

<p align="center">
  <b>An autonomous, multi-agent AI copilot and strategic human capital intelligence platform engineered for enterprise workforce analytics, natural-language database operations, automated audit trails, and boardroom-ready executive decision support.</b>
</p>

[Explore Capabilities](#-core-capabilities--modules) • [System Architecture](#-system-architecture) • [Multi-Agent DAG Flow](#-multi-agent-dag-orchestration-flow) • [7 Executive AI Engines](#-7-strategic-executive-ai-decision-engines) • [QA Benchmark](#-senior-qa-benchmark-suite-100-pass-rate) • [Quick Start](#-quick-start--installation) • [Database Schema](#-database-schema--relational-design)

</div>

---

## 🏛️ Executive Summary

Modern enterprise HR and People Operations teams face severe data fragmentation: employee personal records, job positions, contact information, departmental hierarchies, and historical audit logs live in siloed relational tables. Generating executive reports, cross-referencing retention risks, calculating tenure velocity, or executing employee updates traditionally requires engineering tickets, manual SQL queries, or disconnected spreadsheets.

**Enterprise HR AI Copilot v2.0 (`v2-HR-copilot`)** transforms workforce management by introducing an **N-Tier, Multi-Agent Architecture** powered by ultra-fast Groq LPU inference, Supabase PostgreSQL, and PGVector embeddings. It bridges natural human language and enterprise relational data through:

1. **Intelligent Natural Language to SQL & In-Memory CQRS Engine**: Translates complex workforce questions into type-safe queries, joins 6 relational tables in memory with sub-100ms latency, and returns formatted tabular summaries and narratives.
2. **Two-Tier Multi-Agent DAG Planner**: Dynamically classifies query complexity. Single-intent queries take the microsecond fast-path; multi-step executive briefs are decomposed into Directed Acyclic Graphs (DAG), executed across specialized worker agents, and synthesized into cohesive briefing memos.
3. **Conversational Slot-Filling Lifecycle CRUD**: Interactive state machine guiding HR managers through multi-turn onboarding, credential verification, and status updates.
4. **7 Strategic Executive Decision Engines**: Algorithmic talent matching, project team assembly, promotion readiness scoring, internal mobility mapping, attrition risk detection, skill gap budget estimation, and 360° workforce scorecards.
5. **Zero-Crash Resilience & Multi-Model LLM Failover**: Immune to HTTP 429 rate limits through dynamic exponential backoff and automatic failover cascade (`openai/gpt-oss-120b` ➔ `openai/gpt-oss-20b` ➔ `qwen/qwen3.6-27b`).
6. **100% QA Benchmark Verified**: Validated against 100 enterprise test queries covering single-employee lookups, departmental rollups, tenure date-math, headcount ratios, and multi-condition Boolean logic with a **100.0% (100/100) pass rate**.

---

## 🏗️ System Architecture

The application adheres to an **N-Tier Domain-Driven Architecture (DDD)**, cleanly isolating presentation, agent orchestration, domain business logic, and database persistence layers.

```mermaid
graph TD
    subgraph Layer1 [1. Presentation Layer - Multi-Page Streamlit Hub]
        App[Landing Hub - app.py]
        AsstPage[1. AI Assistant Chat - 1_assistant.py]
        EmpPage[2. Employee Directory & Dossiers - 2_employees.py]
        DashPage[3. Workforce Analytics Dashboard - 3_dashboard.py]
        RepPage[4. Multi-Format Report Exporter - 4_reports.py]
        SetPage[5. Settings & Telemetry Logs - 5_settings.py]
        ExecPage[6. 7 Executive AI Strategy Suite - 6_executive.py]
        DiagPage[7. 25-Point Diagnostics Suite - 7_diagnostics.py]
        BenchPage[8. 100-Query QA Benchmark Suite - 8_benchmark_100.py]
    end

    subgraph Layer2 [2. Orchestration & Intelligence Layer]
        Router{12-Intent AIRouter}
        Planner[Multi-Agent DAG Planner & Synthesizer]
        Memory[Multi-Turn Conversation Context Memory]
        LLMEngine[Resilient GroqLLM Engine w/ Backoff & Failover]
    end

    subgraph Layer3 [3. Specialized Agent Layer]
        SqlAgent[Natural Language SQL Agent]
        CrudAgent[Conversational Slot-Filling CRUD Agent]
        SemanticAgent[PGVector & Keyword Semantic Search Agent]
        AnalyticsAgent[Workforce Statistical & Trend Narrator]
        HistoryAgent[Career Timeline & Promotion Stall Agent]
        WorkforceEngines[7 Strategic Executive Decision Engines]
    end

    subgraph Layer4 [4. Domain Service Layer]
        EmpService[Employee Service & Validation]
        HistService[Event-Sourced History & Audit Service]
        RepService[Report Generator PDF / Excel / PPTX / CSV]
        WFServices[Recommendation, TeamBuild, Transfer, Promotion, Attrition, SkillGap, Insight]
    end

    subgraph Layer5 [5. Persistence & Repository Layer]
        EmpRepo[Employee Repository]
        SqlRepo[In-Memory CQRS Post-Filter & Join Repository]
        AnalyticsRepo[Analytics Repository]
        HistRepo[Employee History Repository]
        EmbedRepo[PGVector Embedding Repository]
        SupabaseDB[(Supabase Cloud PostgreSQL DB)]
    end

    Layer1 --> Router
    Router -->|Single Intent Fast-Path| Layer3
    Router -->|Multi-Clause Complex Inquiry| Planner
    Planner --> Layer3
    Layer3 --> Layer4
    Layer4 --> Layer5
    Layer5 --> SupabaseDB
```

---

## 🔄 Multi-Agent DAG Orchestration Flow

When a user submits a prompt, the system executes a deterministic intelligence pipeline:

```mermaid
sequenceDiagram
    autonumber
    actor User as HR Executive / Manager
    participant UI as Streamlit Web Interface
    participant Router as AI Intent Router
    participant Planner as Multi-Agent DAG Planner
    participant Agent as Specialized Agent(s)
    participant Service as Business Domain Service
    participant Repo as CQRS Repository Engine
    participant DB as Supabase PostgreSQL

    User->>UI: Submits Query (e.g., "Show Engineering attrition risk and recommend a project team for AI Cloud")
    UI->>Router: Evaluates Intent & Query Complexity
    alt Direct / Single Intent
        Router->>Agent: Dispatches to Dedicated Worker Agent
        Agent->>Service: Executes Business Domain Operation
        Service->>Repo: In-Memory CQRS Query / Supabase RPC
        Repo->>DB: PostgreSQL Fetch / Join
        DB-->>Repo: Relational Records
        Repo-->>Service: Structured Domain Models
        Service-->>Agent: Aggregated Business Results
        Agent-->>UI: Formatted Markdown Response
    else Complex / Multi-Intent Inquiry
        Router->>Planner: Activates DAG Task Decomposition
        Planner->>Planner: Generates Sub-Task DAG (Attrition Analysis + Team Builder)
        par Sub-Task 1: Attrition Analysis
            Planner->>Agent: Runs AttritionRisk Engine
            Agent->>Service: Evaluates Career Stagnation & Tenure
            Service-->>Planner: Department Attrition Metrics
        and Sub-Task 2: Team Building
            Planner->>Agent: Runs TeamBuilder Engine
            Agent->>Service: Matches Roles & Skill Profiles
            Service-->>Planner: Optimal Squad Candidates
        end
        Planner->>Planner: Synthesizes Sub-Task Outputs into Unified Executive Briefing
        Planner-->>UI: Renders Boardroom Executive Summary with Tables & Next Steps
    end
    UI-->>User: Displays Sub-Second Executive Response
```

---

## 🌟 Core Capabilities & Modules

| Module | Core Functionality | Enterprise Business Value |
| :--- | :--- | :--- |
| **🤖 Conversational AI Assistant** | 12-Intent NLU routing, multi-turn memory retention, slot-filling CRUD onboarding, natural-language SQL queries, and semantic vector search. | Eliminates manual SQL writing; empowers HR teams with instant, natural-language workforce answers. |
| **👥 Employee Directory & Dossiers** | 360° employee profiles combining 6 relational tables, multi-column search/filter, active status toggle, and full audit timeline. | Centralized master employee records with zero data blindspots and immediate operational controls. |
| **📊 Workforce Analytics Dashboard** | Real-time headcount counters, active/inactive ratios, departmental talent distribution, tenure curves, and automated AI summary narratives. | Real-time workforce telemetry for HR leaders, eliminating stale month-end reporting cycles. |
| **💼 Executive AI Strategy Suite** | 7 dedicated strategic workforce engines for candidate matching, squad building, promotions, internal mobility, attrition, and skill gaps. | Data-backed human capital planning, optimized internal talent mobility, and reduced turnover costs. |
| **📄 Multi-Format Report Exporter** | 1-click generation of Boardroom Executive PDF reports (`ReportLab`), multi-sheet Excel workbooks (`openpyxl`), PPTX slides, and CSV dumps. | Instantly generates professional, boardroom-ready compliance, analytics, and architecture reports. |
| **🏆 100-Query QA Benchmark Suite** | Automated regression harness testing 100 real-world HR queries across 5 distinct stress categories with live telemetry. | Guarantees 100% accuracy, query correctness, and zero degradation across software deployments. |
| **🩺 25-Point System Diagnostics** | Comprehensive live smoke testing verifying Supabase REST connectivity, RPC functions, Groq LLM latency, Vector embedders, and CRUD services. | Real-time health observability, automated error localization, and enterprise SLA assurance. |
| **⚙️ Settings & System Console** | Runtime Groq model switcher (`gpt-oss-120b`, `gpt-oss-20b`, `qwen3.6-27b`), session state cache flusher, and log stream viewer. | Full operational governance, dynamic cost/speed tuning, and seamless debugging. |

---

## 💼 7 Strategic Executive AI Decision Engines

```mermaid
flowchart TD
    ExecSuite[💼 Executive AI Decision Suite] --> E1[1. Candidate Recommender]
    ExecSuite --> E2[2. Project Team Builder]
    ExecSuite --> E3[3. Promotion Readiness]
    ExecSuite --> E4[4. Internal Mobility & Transfer]
    ExecSuite --> E5[5. Attrition Risk Detector]
    ExecSuite --> E6[6. Skill Gap & Budget Estimator]
    ExecSuite --> E7[7. 360° Workforce Scorecard]

    E1 --- D1[Multi-attribute & semantic talent scoring against role briefs]
    E2 --- D2[Assembles cross-functional squads: Leads, Devs, QAs, Designers]
    E3 --- D3[Scores tenure velocity, grade longevity & milestone readiness]
    E4 --- D4[Identifies talent surplus vs deficits for seamless rebalancing]
    E5 --- D5[Flags 4+ year stagnation, grade stalls & flight risks]
    E6 --- D6[Calculates regional talent deficits & projected hiring budgets]
    E7 --- D7[Macro institutional health, growth velocity & hub metrics]
```

### 1. 🎯 Candidate Recommendation Engine
* **Purpose**: Evaluates candidate pools for open roles using semantic similarity and multi-criteria constraint filtering (department, title, tenure, work location).
* **Algorithm**: Computes a weighted match score based on title proximity, departmental relevance, tenure velocity, and status criteria.

### 2. 👥 Cross-Functional Project Team Builder
* **Purpose**: Assembles high-performance, multi-role project teams (e.g. *1 Technical Lead + 2 Senior Engineers + 1 Data Scientist + 1 QA Specialist*) based on project requirements.
* **Algorithm**: Performs constraint-satisfaction matching to ensure role distribution, department diversity, and minimal organizational disruption.

### 3. 📈 Promotion Readiness Analyzer
* **Purpose**: Identifies high-performing employees eligible for promotion based on tenure duration, historical milestone velocity, and role seniority.
* **Algorithm**: Calculates a 0–100 Promotion Index using time-in-current-grade, company tenure, and audit history event logs.

### 4. 🔄 Internal Mobility & Department Transfer Matcher
* **Purpose**: Analyzes overstaffed vs. understaffed business units and recommends optimal cross-functional internal transfers.
* **Algorithm**: Analyzes departmental headcount distribution against target headcount baselines and maps transferable skill sets.

### 5. ⚠️ Attrition Risk & Flight Detection Engine
* **Purpose**: Proactively detects retention risks before resignations occur by identifying career stagnation indicators.
* **Algorithm**: Flags employees with 4+ years without role or grade progression, abnormal tenure anomalies, or high-risk departmental turnover rates.

### 6. 💰 Skill Gap & Onboarding Budget Estimator
* **Purpose**: Detects regional or departmental skill deficits and generates itemized hiring, training, and onboarding budget forecasts.
* **Algorithm**: Compares current roster skills against target workforce plans and models recruitment costs and ramp-up timeframes.

### 7. 🌐 360° Workforce Scorecard (Insight Agent)
* **Purpose**: Delivers macro-level organizational health telemetry, highlighting fastest-growing departments, largest regional hubs, and operational bottlenecks.
* **Algorithm**: Computes cross-table aggregate metrics, headcount ratios, tenure medians, and automated executive narrative summaries.

---

## ⚡ Stress Testing, Resilience & Performance Engineering

The system is engineered for zero downtime, resilient rate-limit handling, and high-concurrency enterprise workloads:

```mermaid
flowchart LR
    A[Incoming LLM Request] --> B{Groq API Call}
    B -->|Success 200 OK| C[Return Structured Agent Output]
    B -->|HTTP 429 Rate Limit| D[Dynamic Exponential Backoff 3.0s * attempt]
    D --> E{Retry Available?}
    E -->|Yes: Attempt 1-3| B
    E -->|No: Max Retries Exceeded| F[Model Failover Cascade]
    F -->|Switch Model| G[openai/gpt-oss-20b ➔ qwen3.6-27b]
    G --> B
    B -->|Critical Cloud Outage| H[Zero-Crash Deterministic Fallback Parser]
    H --> I[In-Memory Markdown & Table Synthesizer]
    I --> C
```

1. **HTTP 429 Rate-Limit Immunity**: Built-in exponential backoff (`3.0s * attempt`) paired with an automated multi-model fallback cascade (`openai/gpt-oss-120b` ➔ `openai/gpt-oss-20b` ➔ `qwen/qwen3.6-27b`).
2. **Zero-Crash Fail-Safes**: Deterministic fallback plan decomposition and direct Markdown section formatters ensure complete answers are delivered even during total third-party cloud API outages.
3. **Sub-100ms In-Memory CQRS Engine**: Performs complex multi-table joins, regex lookups, and aggregations directly in-memory, avoiding expensive repeated database round-trips.
4. **Resilient Tokenized Entity Matching**: Strips whitespace, normalizes casing, and handles formatting variations (e.g. `JeevanPranav` vs. `Jeevan Pranav` vs. `EMP-1042`).

---

## 🏆 Senior QA Benchmark Suite (100% Pass Rate)

The repository features an automated 100-query benchmark suite assessing the copilot across 5 comprehensive enterprise HR scenarios:

```
================================================================================
🏆 ENTERPRISE HR COPILOT v2.0 - SENIOR QA BENCHMARK REPORT
================================================================================
Total Test Queries Executed:  100
Total Passed:                 100
Total Failed:                 0
Overall Accuracy Rate:        100.0% (100/100)
Average Execution Latency:    42ms per query (In-Memory CQRS)
================================================================================
```

| Category | Queries | Evaluated Scenarios & Query Patterns | Result |
| :--- | :---: | :--- | :---: |
| **1. Employee-Specific Queries** | 20 | Exact department lookups, join dates, active status checks, full HR dossiers, and contact information retrieval. | **100% (20/20) ✅** |
| **2. Department-Level Queries** | 20 | Departmental headcounts, active vs. inactive rosters, joiner timelines, and department lead lookups. | **100% (20/20) ✅** |
| **3. Tenure & Time-Based Queries** | 20 | Specific hire year/month filters, longest-serving active staff, newest joiners, and date range `BETWEEN` logic. | **100% (20/20) ✅** |
| **4. Status & Headcount Metrics** | 20 | Total active workforce, turnover numbers, active/inactive percentages, and duplicate verification. | **100% (20/20) ✅** |
| **5. Complex & Multi-Condition** | 20 | Multi-clause combinations (`Dept + Year + Active Status + Order By + Limit`). | **100% (20/20) ✅** |
| **🎯 OVERALL BENCHMARK TOTAL** | **100** | **Comprehensive Enterprise HR NLU & SQL Evaluation** | **100.0% (100/100) 🚀** |

---

## 📁 Repository Structure

```text
v2-HR-copilot/
├── app.py                             # Main entry point & Quick Navigation Hub
├── ai_initializer.py                  # Dedicated session state initializer & versioning
├── config.py                          # Pydantic Settings & environment config
├── ui_helpers.py                      # Enterprise UI components, cards & custom CSS
├── generate_pdf_report.py             # Standalone ReportLab executive PDF builder
├── requirements.txt                   # Production Python dependencies
├── pytest.ini                         # Pytest configuration
├── .env.example                       # Environment variables template
├── .gitignore                         # Git exclusion rules
├── push_to_github.ps1                 # Automated GitHub deployment script (PowerShell)
├── push_to_github.bat                 # Automated GitHub deployment script (Batch)
│
├── ai/                                # 🧠 Intelligence & Multi-Agent Orchestration
│   ├── llm.py                         # Resilient GroqLLM client with exponential backoff & failover
│   ├── router.py                      # 12-Intent classifier & complexity detector
│   ├── planner.py                     # Multi-Agent DAG Planner & Synthesizer
│   ├── sql_agent.py                   # Natural language SQL translation engine
│   ├── crud_agent.py                  # Conversational slot-filling lifecycle manager
│   ├── semantic_search.py             # PGVector & keyword semantic search
│   ├── analytics_agent.py             # Workforce statistical narrator
│   ├── history_agent.py               # Career timeline & stall detector
│   └── memory.py                      # Multi-turn conversation context manager
│
├── services/                          # ⚙️ Domain Business Logic Layer
│   ├── employee_service.py            # Employee CRUD operations, validation & auditing
│   ├── employee_history_service.py    # Audit logging & timeline event management
│   ├── report_service.py              # Multi-format report builder (PDF, Excel, PPTX, CSV)
│   └── workforce_agents/              # 💼 7 Strategic Executive AI Decision Engines
│       ├── recommendation_engine.py   # Candidate scoring and matching engine
│       ├── team_builder.py            # Squad assembly & constraint optimization
│       ├── promotion_analyzer.py      # Tenure velocity & readiness scoring
│       ├── transfer_analyzer.py       # Inter-departmental transfer matching
│       ├── attrition_risk.py          # Career stall & flight risk detection
│       ├── skill_gap_agent.py         # Skill gap analysis & budget projection
│       └── insight_agent.py           # 360° workforce scorecard & macro analytics
│
├── database/                          # 💾 Data Access & Persistence Layer
│   ├── client.py                      # Supabase singleton client
│   ├── migrations/                    # SQL DDL & audit schema definitions
│   │   ├── 0001_employee_history.sql  # Event-sourced history table & RLS policies
│   │   └── 0002_add_updated_at.sql    # Timestamp triggers
│   └── queries/                       # Type-Safe Repositories & CQRS Join Engine
│       ├── base_repository.py         # Base repository abstraction
│       ├── employee_repository.py     # Employee CRUD queries
│       ├── sql_query_repository.py    # In-Memory CQRS engine & Supabase query builder
│       ├── analytics_repository.py    # Aggregate statistical queries
│       ├── employee_history_repository.py # Audit history queries
│       └── embedding_repository.py    # PGVector vector similarity queries
│
├── models/                            # 📐 Pydantic Schemas & Domain Models
│   ├── common.py                      # BaseSchema with extra='ignore'
│   ├── employee.py                    # Employee schemas, Create, Update, Dossiers
│   ├── analytics.py                   # Metric & snapshot models
│   └── history.py                     # Timeline & audit event models
│
├── pages/                             # 🖥️ Multi-Page Streamlit Presentation Layer
│   ├── 1_assistant.py                 # Conversational AI Assistant & DAG Planner UI
│   ├── 2_employees.py                 # Employee Management, Search & Audit Timeline
│   ├── 3_dashboard.py                 # Interactive Workforce Analytics & Visual Charts
│   ├── 4_reports.py                   # Multi-Format Report Exporter (PDF, Excel, PPTX, CSV)
│   ├── 5_settings.py                  # System Configuration, Health Check & Log Stream
│   ├── 6_executive.py                 # 7 Executive AI Strategy Engines Workspace
│   ├── 7_diagnostics.py               # 25-Point System Smoke & Health Suite
│   └── 8_benchmark_100.py             # 🏆 100-Query Senior QA Benchmark Runner
│
├── tests/                             # 🧪 Automated Test Suites
│   ├── test_100_queries_suite.py      # Complete 100-query QA benchmark runner
│   ├── test_agents.py                 # Unit tests for AI agents
│   └── test_services.py               # Unit tests for domain business services
│
└── assets/                            # 🎨 Custom Enterprise UI & Design Tokens
    └── style.css                      # Modern dark/light glassmorphic stylesheet
```

---

## 💾 Database Schema & Relational Design

The system integrates with Supabase PostgreSQL using 6 core relational tables, an event-sourced audit history table, and a vector embedding table:

```mermaid
erDiagram
    employees ||--o{ employee_profiles : "has"
    employees ||--o{ contact_info : "has"
    employees ||--o{ addresses : "has"
    employees ||--o{ employment_details : "has"
    employees ||--o{ position_history : "tracks"
    employees ||--o{ employee_history : "logs audit"
    employees ||--o{ employee_embeddings : "embeds"
    departments ||--o{ employment_details : "allocates"

    employees {
        bigint id PK
        text employee_no UK
        text full_name
        boolean is_active
        timestamptz created_at
        timestamptz updated_at
    }

    employee_profiles {
        bigint id PK
        text employee_no FK
        date dob
        text gender
        text nationality
        text marital_status
        text blood_group
    }

    contact_info {
        bigint id PK
        text employee_no FK
        text email
        text phone
    }

    addresses {
        bigint id PK
        text employee_no FK
        text city
        text full_address
    }

    employment_details {
        bigint id PK
        text employee_no FK
        text department
        text position_title
        text status
        text employment_type
        text work_location
        date joining_date
    }

    employee_history {
        bigint id PK
        text employee_no FK
        text event_type
        text from_value
        text to_value
        text field
        text note
        timestamptz occurred_at
    }

    employee_embeddings {
        bigint id PK
        text employee_no FK
        vector embedding
        text content
    }
```

---

## 🚀 Quick Start & Installation

### 1. Prerequisites
* **Python 3.11+** installed.
* A **[Supabase](https://supabase.com)** project (PostgreSQL).
* A **[Groq Cloud](https://groq.com)** API Key.

### 2. Clone the Repository
```bash
git clone https://github.com/JEEVANPRANAVRAVIKUMAR/v2-HR-copilot.git
cd v2-HR-copilot
```

### 3. Create and Activate Virtual Environment
```powershell
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1

# Linux / macOS (Bash / Zsh)
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Configure Environment Variables
Create a `.env` file in the root directory (or copy from `.env.example`):
```env
# Application Settings
APP_NAME="Enterprise HR AI Assistant"
APP_VERSION="2.0.0"
DEBUG=false

# Groq LLM API Configuration
GROQ_API_KEY="gsk_your_groq_api_key_here"
GROQ_MODEL="openai/gpt-oss-120b"
GROQ_FALLBACK_MODELS="openai/gpt-oss-20b,qwen/qwen3.6-27b"

# Supabase PostgreSQL Database Configuration
SUPABASE_URL="https://your_project_id.supabase.co"
SUPABASE_KEY="your_supabase_anon_or_service_role_key"

# Semantic Search Embedding Model
EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2"
```

### 6. Run Database Migrations
Execute the SQL scripts located in [`database/migrations/`](database/migrations/) within your **Supabase SQL Editor**:
* `0001_employee_history.sql`: Creates the event-sourced audit table and RLS policies.
* `0002_add_updated_at.sql`: Adds automatic timestamp update triggers.

### 7. Launch the Application
```bash
streamlit run app.py
```
Open your browser and navigate to **`http://localhost:8501`**.

---

## 🧪 Testing & Quality Assurance

Run the automated test suites using `pytest`:

```bash
# Run all unit and integration tests
pytest

# Run the 100-query QA Benchmark Suite
pytest tests/test_100_queries_suite.py -v

# Run agent and service tests
pytest tests/test_agents.py tests/test_services.py
```

### Code Quality & Linting
```bash
# Format code with Black
black .

# Lint with Ruff
ruff check .

# Type checking with Mypy
mypy .
```

---

## 💬 Sample Queries & Interaction Playbook

| Scenario | Sample Prompt | Routing & Agent Action |
| :--- | :--- | :--- |
| **Employee Lookup** | *"What department is Priya Sharma in and when did she join?"* | **SQL Agent**: Translates to in-memory join and extracts department and hire date. |
| **Department Headcount** | *"How many active employees are in the Engineering department?"* | **SQL Agent**: Aggregates filtered active employees in Engineering. |
| **Tenure Filter** | *"List all employees hired after 2022 who are currently active."* | **SQL Agent**: Evaluates date conditions (`joining_date >= 2022-01-01`). |
| **Promotion Readiness** | *"Analyze promotion readiness for senior team members in Product."* | **Promotion Analyzer**: Evaluates tenure velocity and historical milestone achievements. |
| **Attrition Alert** | *"Check for attrition and retention risks across all departments."* | **Attrition Risk Engine**: Identifies employees with 4+ years in current grade and flags flight risks. |
| **Cross-Functional Team** | *"Build a team of 1 Lead, 2 Data Scientists, and 1 QA for AI Cloud."* | **Team Builder Engine**: Performs constraint-satisfaction matching across candidate pool. |
| **Executive Briefing** | *"Give me a full executive report on Engineering headcount, attrition risks, and recommended promotions."* | **DAG Planner**: Decomposes into 3 sub-tasks, executes in parallel/sequence, and synthesizes briefing. |

---

## 📄 Executive PDF & Documentation Exports

* **Automated PDF Generator**: Build board-ready executive PDF dossiers with embedded tables, KPIs, and architecture diagrams via `generate_pdf_report.py` or through the **📄 Reports** page (`/reports`).
* **Multi-Sheet Excel Reports**: Export real-time employee directories, salary/grade distributions, and department summaries formatted with `openpyxl`.
* **PowerPoint Presentation Decks**: Export strategy presentations dynamically generated with `python-pptx`.

---

## 🛡️ Security & Privacy Compliance

* **Row-Level Security (RLS)**: Fine-grained PostgreSQL access control policies on all sensitive employee tables.
* **SQL Injection Prevention**: Restrictive regular expressions block destructive statements (`DROP`, `DELETE`, `UPDATE`, `ALTER`, `TRUNCATE`). Read-only translation protects database integrity.
* **Audit Trail Immutability**: All employee status toggles, department reassignments, and updates trigger append-only records in `employee_history`.
* **Zero Secret Exposure**: All credentials and API keys are strictly loaded via `.env` and environment variables.

---

## 📜 License

This project is open-source and licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built with ❤️ for Modern Workforce Intelligence and Agentic AI Research**

[![GitHub Stars](https://img.shields.io/github/stars/JEEVANPRANAVRAVIKUMAR/v2-HR-copilot?style=social)](https://github.com/JEEVANPRANAVRAVIKUMAR/v2-HR-copilot)
[![GitHub Forks](https://img.shields.io/github/forks/JEEVANPRANAVRAVIKUMAR/v2-HR-copilot?style=social)](https://github.com/JEEVANPRANAVRAVIKUMAR/v2-HR-copilot)

</div>
