# Forge Roadmap

> **Status**: v1.0.0 in active development

## v1.0.0 — The Core Engine ✅ Current

Ships with everything needed to run AI-orchestrated goals locally.

### Execution Engine
- [x] RulePlanner — deterministic, offline
- [x] LLMPlanner — Ollama, OpenAI, Anthropic, Gemini
- [x] FallbackPlanner — LLM with rule-based fallback
- [x] 7 Executor types (CLI, Shell, Python, Git, Docker, MCP, Model)
- [x] CompositeVerifier (exit code, files, output patterns)
- [x] CircuitBreakerRetryController with infinite loop detection
- [x] RollingContextOptimizer

### Memory
- [x] SQLite-backed execution memory
- [x] Structured log entries per execution
- [x] Context summaries
- [x] Execution statistics

### Interfaces
- [x] FastAPI REST API (full CRUD + WebSocket)
- [x] Typer + Rich CLI (8 commands)
- [x] Plugin SDK (IPlugin interface + PluginManager)

### Infrastructure
- [x] Docker + docker-compose
- [x] GitHub Actions CI
- [x] ILearningInterface (stub — no implementation)

---

## v1.1.0 — Dashboard 🖥️ Planned Q3 2026

Visual execution monitoring without leaving your browser.

- [ ] Next.js 14 dashboard (TypeScript, Tailwind, shadcn/ui, dark mode)
- [ ] Active executions overview
- [ ] Execution detail: task list + token usage + logs
- [ ] Settings page (configure API endpoint)
- [ ] Real-time updates via WebSocket polling

---

## v1.2.0 — VS Code Extension 🔌 Planned Q4 2026

Run Forge goals directly from your editor.

- [ ] `Forge: Run Goal` command
- [ ] `Forge: Show Status` output panel
- [ ] `Forge: Show Logs` log streaming

---

## v2.0.0 — Scale ⚡ 2026

For power users and production deployments.

- [ ] Parallel DAG execution (concurrent independent tasks)
- [ ] Distributed workers (Redis-backed job queue)
- [ ] PostgreSQL support
- [ ] Advanced context compression (semantic deduplication)
- [ ] Learning engine — pattern recognition from past execution history
- [ ] Execution templates (reusable task DAGs)
- [ ] Forge Hub — community plugin registry

---

## Enterprise Edition (Future)

Available as a separate commercial product:

- RBAC and SSO authentication
- Team workspaces
- Audit logging
- Managed cloud deployment
- Vector memory (semantic search over past executions)
- Advanced analytics and dashboards
- SLA guarantees
- Priority support

---

## How to Influence the Roadmap

1. **Open a Discussion** — Share your use case and feature request
2. **Vote on Issues** — 👍 on issues you want prioritized
3. **Contribute** — PRs are always welcome — see [CONTRIBUTING.md](CONTRIBUTING.md)
