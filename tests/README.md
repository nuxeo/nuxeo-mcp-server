# Nuxeo MCP Test Suite

This test suite validates the functionality of the Nuxeo MCP Server.

## Running Tests

### Prerequisites

- Python 3.11+
- Required packages: `pip install -r requirements.txt`
- (Optional) Docker for integration tests
- Valid Nuxeo server credentials for live server tests

### Test Categories

1. **Unit Tests** - Test individual components without external dependencies
2. **Integration Tests** - Test with a Docker-based Nuxeo instance  
3. **Live Server Tests** - Test against the live Nuxeo server (currently configured to be https://nightly-2023.nuxeocloud.com/nuxeo)

### Running Tests

#### Option 1: With Environment Variables (Recommended for CI/CD)

```bash
export NUXEO_TEST_USERNAME='your_username'
export NUXEO_TEST_PASSWORD='your_password'
python -m pytest tests/
```

#### Option 2: With Interactive Prompt

```bash
# Use -s flag to allow interactive credential input
python -m pytest tests/ -s
```

You'll be prompted once per session for credentials.

#### Option 3: Using a .env File

Create a `.env` file in the project root:
```
NUXEO_TEST_USERNAME=your_username
NUXEO_TEST_PASSWORD=your_password
```

Then run:
```bash
python -m pytest tests/
```

### Common Test Commands

```bash
# Run all tests (excluding integration tests)
python -m pytest tests/ --no-integration

# Run only unit tests
python -m pytest tests/ -m "not integration"

# Run with verbose output
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_search_tools.py

# Run a specific test
python -m pytest tests/test_operations_fix.py::test_void_operation

# Run with coverage
python -m pytest tests/ --cov=nuxeo_mcp

# Run integration tests (requires Docker)
python -m pytest tests/ --integration
```

### Test Structure

- `conftest.py` - Pytest configuration and fixtures
- `test_*.py` - Test files (automatically discovered by pytest)
- `test_credentials.py` - Credential management helper

### Authentication

Tests that connect to the live Nuxeo server at `https://nightly-2023.nuxeocloud.com/nuxeo` require valid credentials. 

If credentials are not provided via environment variables, you will see a message with instructions on how to provide them.

### Troubleshooting

**Tests fail with "Unauthorized" errors:**
- Ensure you have valid credentials for the Nuxeo server
- Check that environment variables are set correctly

**No credential prompt appears:**
- Run pytest with the `-s` flag: `python -m pytest tests/ -s`
- Or set environment variables before running tests

**Integration tests are skipped:**
- Use the `--integration` flag to run integration tests
- Ensure Docker is installed and running

**Import errors:**
- Ensure you're in the project root directory
- Install dependencies: `pip install -r requirements.txt`