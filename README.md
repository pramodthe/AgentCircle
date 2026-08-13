# AgentCircle

Spec-driven project scaffold (Kiro-style workflow, without `.kiro`).

## Spec layout

```
spec/
├── steering/   # Product, tech, structure, API, testing, security
├── hooks/      # Reusable agent workflow prompts
└── specs/      # Feature specs (requirements → design → tasks)
```

See [spec/README.md](spec/README.md).

## Getting started

1. Fill in `spec/steering/*.md`
2. Refine `spec/specs/agentcircle-core/`
3. Execute tasks in `tasks.md` in order
4. Add new features with:

```bash
mkdir -p spec/specs/<feature-name>
cp spec/specs/_template/* spec/specs/<feature-name>/
```

## Repo

- Remote: https://github.com/pramodthe/AgentCircle
