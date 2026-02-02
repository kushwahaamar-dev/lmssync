# Contributing to Canvas Outlook Sync

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/kushwahaamar-dev/lmssync.git
   cd canvas_outlook_sync
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   make install-dev
   ```

## Development Workflow

### Running Tests
```bash
make test          # Run tests
make test-cov      # Run tests with coverage
```

### Code Quality
```bash
make lint          # Run linting
make format        # Format code
make typecheck     # Run type checking
```

### Testing Your Changes
```bash
make dry-run       # Test sync without making changes
make health        # Check API connectivity
```

## Code Style

- We use **Black** for code formatting (line length: 100)
- We use **isort** for import sorting
- We use **ruff** for linting
- We use **mypy** for type checking

Run `make format` before committing to ensure consistent style.

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting (`make test lint typecheck`)
5. Commit with a descriptive message
6. Push to your fork
7. Open a Pull Request

## Commit Message Format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` - New features
- `fix:` - Bug fixes
- `docs:` - Documentation changes
- `test:` - Test additions/changes
- `chore:` - Maintenance tasks
- `ci:` - CI/CD changes

Example: `feat: add health check command`

## Questions?

Feel free to open an issue for any questions or concerns.
