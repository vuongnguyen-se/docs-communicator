# Initial Prompt for Your AI Coding Platform

You are helping me build **CloudDocs AI**, a portfolio project: a serverless, AI-powered document assistant on AWS.

First, read all Markdown files in the project root, especially `AI_CODING_RULES.md`, `ARCHITECTURE.md`, `PROJECT_REQUIREMENTS.md`, and `TASKS.md`. Treat them as the project context and source of truth.

## Your first assignment

Do not build the entire application yet.

1. Inspect the current repository and report what already exists.
2. Compare the repository with the documented target structure.
3. Identify missing decisions or contradictions.
4. Recommend a minimal Phase 0 / Phase 1 implementation plan.
5. Propose the initial folder structure and explain each folder.
6. Identify AWS prerequisites and Region-specific checks, especially Amazon Bedrock Knowledge Bases, model access, and vector-store availability.
7. Do not create AWS resources or deploy anything.
8. Do not add services beyond the current milestone.
9. Ask me to approve the plan before making broad code changes.

## Teaching expectations

I am learning cloud architecture while building this project. Explain technical decisions in a practical, beginner-friendly way. Explain the purpose of each AWS service and how requests/data move between them.

When I approve implementation, work in small increments. For each increment:
- State the objective.
- List files to create or modify.
- Implement the smallest useful change.
- Add or update tests.
- Explain how I can run and verify it.
- Update `TASKS.md` and relevant documentation.

Do not claim that code, tests, AWS resources, or deployments succeeded unless you actually verified them.
