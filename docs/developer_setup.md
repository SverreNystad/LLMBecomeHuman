# Developer Setup

## Prerequisites

Before you can start developing, make sure you have the following installed:

- **Git**: Ensure that git is installed on your machine. [Download Git](https://git-scm.com/downloads)
- **Docker**: Ensure that Docker is installed on your machine. [Download Docker](https://www.docker.com/products/docker-desktop)
- **Python**: Ensure that Python 3.8 or higher is installed on your machine. [Download Python](https://www.python.org/downloads/)
- **UV**: Ensure that [uv](https://github.com/astral-sh/uv) is installed on your machine. [Download UV](https://github.com/astral-sh/uv)
- **pre-commit**: Ensure that [pre-commit](https://pre-commit.com/) is installed on your machine. [Download pre-commit](https://pre-commit.com/)

### Run Pre-commit Hooks

```bash
uv run pre-commit run --all-files
```

### Generate Documentation Site

To build and preview the documentation site locally:

```bash
uv run mkdocs build
uv run mkdocs serve
```

This will build the documentation and start a local server at [http://127.0.0.1:8000/](http://127.0.0.1:8000/) where you can browse the docs and API reference. Get the documentation according to the latest commit on main by viewing the `gh-pages` branch on GitHub: [https://sverrenystad.github.io/LLMBecomeHuman/](sverrenystad.github.io/LLMBecomeHuman/).
