# Contributing to evtx2es
Thank you for your interest in contributing to evtx2es!

## Getting Started
### Development Setup

**Recommended: Using Dev Container**

This project includes a dev container configuration for consistent development environment:

1. Fork the repository on GitHub
2. Clone your fork locally:

```bash
$ git clone https://github.com/your-username/evtx2es.git
$ cd evtx2es
```

3. Open in VS Code with Dev Container extension, or use the provided dev container

**Alternative: Local Setup**

```bash
$ pip install uv
$ uv sync --dev
```

**Editor**: This project is developed using Cursor with custom rules (currently being organized).

### Running Tests

```bash
$ uv run pytest
```

### Code Style
This project uses:
- **black** for code formatting
- **flake8** for linting
- **mypy** for type checking

## Contributing
### Reporting Issues
- Use GitHub Issues to report bugs or request features

### Pull Requests
1. Create a feature branch from `master`
2. Make your changes
3. Add tests if applicable
4. Ensure all tests pass
5. Submit a pull request

### Guidelines
- Follow existing code style and patterns
- Update documentation if needed

## Requirements
- Python 3.11+
- Dependencies listed in `pyproject.toml`

## License
By contributing, you agree that your contributions will be licensed under the MIT License.

## Questions?
Feel free to open an issue for discussion or reach out to the maintainers.

Thank you for contributing! :sushi: :sushi: :sushi: 
