# Contributing to ClaudeKit

Thank you for your interest in contributing to ClaudeKit! This guide will help you get started.

## How to Contribute

### Reporting Issues

- Use [GitHub Issues](https://github.com/omarmokhtar/claudekit/issues) to report bugs or request features
- Check existing issues first to avoid duplicates
- Use the provided issue templates

### Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Run the test suite: `python3 -m pytest tests/ -v`
5. Commit with a descriptive message following [Conventional Commits](https://www.conventionalcommits.org/)
6. Push and create a Pull Request

### Development Setup

```bash
git clone https://github.com/omarmokhtar/claudekit.git
cd claudekit
pip install -r tests/requirements.txt
python3 -m pytest tests/ -v
```

### Adding a New Skill

1. Create a directory under `.claude/skills/your-skill-name/`
2. Add a `SKILL.md` file with YAML frontmatter (`name`, `description`)
3. Follow the skill writing guide in `docs/SKILLS.md`
4. Update `.claude/skills/skills-registry.json`
5. Add tests in `tests/`

### Adding a New Agent

1. Create an agent file in `.claude/agents/your-agent.md`
2. Use the agent template from `.claude/agents/_shared/AGENT_TEMPLATE.md`
3. Add a corresponding command in `.claude/commands/`
4. Update documentation in `docs/AGENTS.md`

### Code Style

- Shell scripts: Use `shellcheck` for linting
- Python: Follow PEP 8
- Markdown: One sentence per line where practical

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
