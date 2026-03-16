# Developer Guide

This guide provides information for developers who want to build, run tests, and extend the Nuxeo MCP Server.

## Setting Up the Development Environment

1. Clone the repository:

```bash
git clone https://github.com/nuxeo/nuxeo-mcp-server.git
cd nuxeo-mcp-server
```

2. Install dependencies:

<details open>
<summary>Using uv (recommended)</summary>

Install [uv](https://docs.astral.sh/uv/) if you don't have it:

```bash
brew install uv
# Or: curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then install all dependencies (including dev extras) from the lock file:

```bash
uv sync --frozen --extra dev
```

uv automatically creates a `.venv` virtual environment and installs all dependencies from `uv.lock`, ensuring a fully reproducible environment.

</details>

<details>
<summary>Using pip</summary>

```bash
# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# On Unix/macOS:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install the package in development mode
pip install -e ".[dev]"
```

</details>

## Building the Project

<details open>
<summary>Using uv (recommended)</summary>

```bash
# Build the package (produces sdist and wheel in dist/)
uv build
```

</details>

<details>
<summary>Using pip</summary>

```bash
pip install build
python -m build
```

</details>

## Running Tests

The project includes a comprehensive test suite using pytest with different test categories.

### Unit Tests

<details open>
<summary>Using uv (recommended)</summary>

```bash
uv run pytest tests/ -v --no-integration
```

</details>

<details>
<summary>Using pip</summary>

```bash
# Run unit tests only
python -m pytest tests/ -v --no-integration
```

</details>

### Integration Tests

Integration tests require a running Nuxeo server (automatically managed via Docker):

<details open>
<summary>Using uv (recommended)</summary>

```bash
# With standard Docker
uv run pytest tests/ -v --integration

# With Rancher Desktop
uv run pytest tests/ -v --integration --rancher

# With environment variable
USE_RANCHER=true uv run pytest tests/ -v --integration
```

</details>

<details>
<summary>Using pip</summary>

```bash
# With standard Docker
python -m pytest tests/ -v --integration

# With Rancher Desktop
python -m pytest tests/ -v --integration --rancher

# With environment variable
USE_RANCHER=true python -m pytest tests/ -v --integration
```

</details>

### Test Categories

- **Unit Tests**: Tests that don't require external services and use mocks
- **Integration Tests**: Tests that require a running Nuxeo server

### Debugging Tests

For more verbose output during tests:

<details open>
<summary>Using uv (recommended)</summary>

```bash
# Enable verbose output
uv run pytest -v

# Show print statements and real-time output
uv run pytest -s

# Show logs
uv run pytest --log-cli-level=INFO
```

</details>

<details>
<summary>Using pip</summary>

```bash
# Enable verbose output
python -m pytest -v

# Show print statements and real-time output
python -m pytest -s

# Show logs
python -m pytest --log-cli-level=INFO
```

</details>

## Running Nuxeo with Docker

For development and testing, you can run a Nuxeo server using Docker:

```bash
# Pull the Nuxeo image
docker pull nuxeo/nuxeo:latest

# Run Nuxeo container
docker run -d --name nuxeo -p 8080:8080 \
  -e NUXEO_DEV_MODE=true \
  -e NUXEO_PACKAGES="nuxeo-web-ui" \
  nuxeo/nuxeo:latest

# Check if Nuxeo is running
docker ps | grep nuxeo

# View Nuxeo logs
docker logs -f nuxeo
```

Access the Nuxeo server at http://localhost:8080/nuxeo with default credentials Administrator/Administrator.

### Seeding the Nuxeo Repository with Test Data

The project includes a script to initialize the Nuxeo repository with sample documents for testing:

<details open>
<summary>Using uv (recommended)</summary>

```bash
# Run the seed script with default settings
uv run python seed_nuxeo.py

# Or with custom settings
uv run python seed_nuxeo.py --url http://mynuxeo.example.com/nuxeo --username admin --password secret
```

</details>

<details>
<summary>Using pip</summary>

```bash
# Run the seed script with default settings
python seed_nuxeo.py

# Or with custom settings
python seed_nuxeo.py --url http://mynuxeo.example.com/nuxeo --username admin --password secret
```

</details>

This script will:
1. Create a folder in the Nuxeo workspaces
2. Create a File document with a dummy PDF attachment
3. Create a Note document with random text

The script outputs the paths and IDs of the created documents, which can be used for testing the MCP server.

## Updating Dependencies

<details open>
<summary>Using uv (recommended)</summary>

```bash
# Update the lock file after modifying pyproject.toml
uv lock

# Upgrade all dependencies to their latest allowed versions
uv lock --upgrade

# Add a new dependency
uv add <package>

# Add a new dev dependency
uv add --optional dev <package>
```

</details>

<details>
<summary>Using pip</summary>

```bash
# Install a new dependency, then add it manually to pyproject.toml
pip install <package>

# Upgrade all dependencies
pip install --upgrade -e ".[dev]"
```

> Note: pip does not generate a lock file.

</details>

## Project Structure

```
nuxeo-mcp/
├── src/
│   └── nuxeo_mcp/
│       ├── __init__.py
│       ├── __main__.py
│       ├── server.py
│       ├── tools.py
│       ├── resources.py
│       └── utility.py
├── tests/
│   ├── conftest.py
│   ├── test_basic.py
│   ├── test_server.py
│   ├── test_integration.py
│   ├── test_document_tools.py
│   └── test_utility.py
├── specs/
│   ├── 01_init.md
│   ├── 02_tests.md
│   ├── 03_seed.md
│   ├── 04_type_hinting.md
│   ├── 05_simplify.md
│   └── ...
├── .github/
│   └── workflows/
│       ├── build-and-unit-tests.yml
│       └── integration-tests.yml
├── seed_nuxeo.py
├── pyproject.toml
├── README.md
├── DEVELOPER.md
└── USAGE.md
```

## Adding New Tools

To add a new tool to the MCP server, add a new function in the `tools.py` file:

```python
# In src/nuxeo_mcp/tools.py
def register_tools(mcp, nuxeo) -> None:
    # ... existing tools ...
    
    @mcp.tool(
        name="your_tool_name",
        description="Description of your tool",
        input_schema={
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "Description of param1",
                },
            },
            "required": ["param1"],
        },
    )
    def your_tool_name(args: Dict[str, Any]) -> Dict[str, Any]:
        """Your tool implementation."""
        # Implementation here
        return {"result": "Your result"}
```

## Adding New Resources

To add a new resource to the MCP server, add a new function in the `resources.py` file:

```python
# In src/nuxeo_mcp/resources.py
def register_resources(mcp, nuxeo) -> None:
    # ... existing resources ...
    
    @mcp.resource(
        uri="nuxeo://your-resource",
        name="Your Resource Name",
        description="Description of your resource",
    )
    def get_your_resource() -> Dict[str, Any]:
        """Your resource implementation."""
        # Implementation here
        return {"result": "Your result"}
```

## Utility Functions

The `utility.py` module provides utility functions for working with Nuxeo documents and other common tasks:

### Document Formatting

The `format_doc` function formats a Nuxeo document as markdown text:

```python
from nuxeo_mcp.utility import format_doc

# Get a document from Nuxeo
doc = nuxeo.client.get_document('/path/to/document')

# Format the document as markdown
markdown = format_doc(doc)
print(markdown)
```

The formatted output includes:
- Basic document information (UID, type, title, path, facets)
- Document flags (isProxy, isCheckedOut, isTrashed, isVersion)
- Document properties grouped by namespace in markdown tables

## Code Style and Conventions

- We use [Black](https://black.readthedocs.io/) for code formatting
- We use [isort](https://pycqa.github.io/isort/) for import sorting
- We use [mypy](https://mypy.readthedocs.io/) for type checking
- We use [pytest](https://docs.pytest.org/) for testing

Run style tools:

<details open>
<summary>Using uv (recommended)</summary>

```bash
uv run black src/ tests/
uv run isort src/ tests/
uv run mypy src/
```

</details>

<details>
<summary>Using pip</summary>

```bash
python -m black src/ tests/
python -m isort src/ tests/
python -m mypy src/
```

</details>

## GitHub Actions Workflows

The project includes three GitHub Actions workflows, all using [uv](https://docs.astral.sh/uv/) for fast, reproducible dependency installation via the shared `.github/actions/setup-and-install-dep` composite action:

1. **Build and Unit Tests**: Builds the project with `uv build` and runs unit tests on push to the main branch and on pull requests.
2. **Integration Tests**: Runs integration tests with the Nuxeo Docker image on push to the main branch and on pull requests.
3. **Package Docker Image**: Builds, tests, and pushes the Docker image.

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -am 'Add my feature'`
4. Push to the branch: `git push origin feature/my-feature`
5. Submit a pull request
