# Developer Guide

This guide provides information for developers who want to build, run tests, and extend the Nuxeo MCP Server.

## Setting Up the Development Environment

1. Clone the repository:

```bash
git clone https://github.com/nuxeo/nuxeo-mcp-server.git
cd nuxeo-mcp-server
```

2. Create a virtual environment and install dependencies:

```bash
# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Unix/macOS:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install the package in development mode
pip install -e ".[dev]"
```

## Building the Project

```bash
# Build the package
python -m build

# This will create distribution files in the dist/ directory
```

## Running Tests

The project includes a comprehensive test suite using pytest with different test categories.

### Unit Tests

```bash
# Run unit tests only
python -m pytest tests/ -v --no-integration
```

### Integration Tests

Integration tests require a running Nuxeo server (automatically managed via Docker):

```bash
# With standard Docker
python -m pytest tests/ -v --integration

# With Rancher Desktop
python -m pytest tests/ -v --integration --rancher

# With environment variable
USE_RANCHER=true python -m pytest tests/ -v --integration
```

### Test Categories

- **Unit Tests**: Tests that don't require external services and use mocks
- **Integration Tests**: Tests that require a running Nuxeo server

### Debugging Tests

For more verbose output during tests:

```bash
# Enable verbose output
pytest -v

# Show print statements and real-time output
pytest -s

# Show logs
pytest --log-cli-level=INFO
```

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

```bash
# Run the seed script with default settings
python seed_nuxeo.py

# Or with custom settings
python seed_nuxeo.py --url http://mynuxeo.example.com/nuxeo --username admin --password secret
```

This script will:
1. Create a folder in the Nuxeo workspaces
2. Create a File document with a dummy PDF attachment
3. Create a Note document with random text

The script outputs the paths and IDs of the created documents, which can be used for testing the MCP server.

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

## GitHub Actions Workflows

The project includes two GitHub Actions workflows:

1. **Build and Unit Tests**: This workflow builds the project and runs unit tests on push to the main branch and on pull requests.
2. **Integration Tests**: This workflow runs integration tests with the Nuxeo Docker image on push to the main branch and on pull requests.

### Build and Unit Tests Workflow

The Build and Unit Tests workflow:
- Sets up Python 3.10
- Installs dependencies
- Builds the project
- Runs unit tests

### Integration Tests Workflow

The Integration Tests workflow:
- Sets up Python 3.10
- Installs dependencies
- Authenticates with the Nuxeo Docker registry
- Pulls the Nuxeo Docker image
- Runs integration tests

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -am 'Add my feature'`
4. Push to the branch: `git push origin feature/my-feature`
5. Submit a pull request
