# Contributing to OpenHer

Thank you for your interest in OpenHer! Every contribution matters — whether it's a new persona, a skill plugin, a bug fix, or documentation improvements.

## 🚀 Getting Started

1. **Fork** this repo and clone your fork
2. Create a virtual environment: `python -m venv .venv && source .venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Create a feature branch: `git checkout -b feature/your-feature`

## 📐 Code Guidelines

### Style

- **Python 3.11+** — use modern syntax (type hints, `match`, `|` unions)
- Follow [PEP 8](https://peps.python.org/pep-0008/) conventions
- Use `async/await` for all I/O-bound operations
- Keep functions focused — if it does two things, split it

### Naming

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`

### Architecture Principles

- **Never modify the persona engine** for feature-specific logic — use the Skill Engine instead
- Skills are self-contained: each skill lives in its own directory with a `SKILL.md`
- Providers follow the adapter pattern in `providers/`
- Keep prompt logic in prompt builders, not in engine code

## 🧪 Testing

Before submitting a PR, please ensure:

```bash
# Run the test suite
python -m pytest tests/ -v

# Run specific test modules
python -m pytest tests/test_genome_engine.py -v
python -m pytest tests/test_chat_agent.py -v
```

- Write tests for new features — especially for engine logic and skill behavior
- Use `pytest` with `pytest-asyncio` for async tests
- Mock external API calls (LLM providers, EverMemOS) — don't rely on live services in tests

## 🎭 Adding a New Persona

1. Create a directory under `persona/personas/your_character/`
2. Add a `SOUL.md` with genome seed configuration (see [Persona Creation Guide](docs/persona_creation_guide.md))
3. **Do not write personality descriptions** — personality emerges from drives and engine parameters
4. Test with at least 2 different LLM providers to verify persona differentiation

## 🛠️ Adding a New Skill

1. Create a directory under `skills/your_skill/`
2. Add a `SKILL.md` with frontmatter (`name`, `description`, `keywords`, `type`)
3. Implement tool functions if needed
4. Add tests under `tests/`
5. See existing skills (`split_messages`, `weather`, `photo`) for reference

## 📝 Commit Messages

Use clear, descriptive commit messages:

```
feat: add voice emotion detection skill
fix: correct drive metabolism decay when session is idle
docs: update LLM compatibility table with MiniMax results
refactor: extract prompt builder from chat_agent
test: add Hebbian learning convergence tests
```

## 🔀 Pull Request Process

1. Update documentation if your change affects user-facing behavior
2. Ensure all tests pass
3. Keep PRs focused — one feature or fix per PR
4. Describe **what** changed and **why** in the PR description
5. Link related issues if applicable

## 🐛 Reporting Issues

When filing an issue, please include:

- Python version and OS
- LLM provider and model being used
- Steps to reproduce
- Expected vs. actual behavior
- Relevant logs (with API keys redacted)

## 💬 Questions?

Open a [Discussion](https://github.com/kellyvv/OpenHer/discussions) for questions, ideas, or general feedback.

---

Thank you for helping grow OpenHer 🧬
