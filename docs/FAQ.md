# Forge Frequently Asked Questions (FAQ)

### What is Forge?
Forge is an open-source execution runtime that sits between AI models and external tools. It acts as an execution layer that plans, executes, verifies, and retries tasks recursively until a user-provided goal is completed.

### Is Forge another MCP (Model Context Protocol) Server?
No. MCP is a standard communication protocol that lets models query tools. Forge is an orchestration/execution layer that *hosts* MCP clients, runs local shell/python code execution, applies retry circuit breakers, optimizes context windows, and provides safety boundaries (like blocking `git push` operations).

### Does Forge require an API Key?
No. By default, Forge runs fully locally using Ollama (Llama 3.2 3B). You can optionally configure it to use cloud model providers like OpenAI, Anthropic, or Gemini.

### How do I write a custom task executor?
You can extend Forge by creating a plugin. Simply inherit from the `IPlugin` class, declare your manifest `forge_plugin.json`, and place it in the `plugins/` directory. Check out the **[Plugin SDK Guide](PLUGINS.md)** for detailed instructions.

### Is Forge ready for distributed deployments?
No, Version 1 Community Edition is optimized for local single-node execution using SQLite. The architecture is designed to support distributed worker queues (like Celery/Redis) and Postgres backends, which are planned for future versions.
