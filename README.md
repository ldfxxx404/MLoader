# MLoader

MLoader is a tool for resolving and downloading media content with built-in playback and metadata management

## Tech Stack
- **Language**: Python 3.13+
- **UI Framework**: PySide6 (Qt for Python)
- **Networking**: `requests`
- **Audio Metadata**: `mutagen`
- **Testing**: `pytest`
- **Linting**: `ruff`

## Project Structure
- `src/mloader/downloader`: Logic for resolving URLs and downloading files
- `src/mloader/gui`: User interface components and GUI-specific services
- `src/mloader/player`: Media playback management using `QtMultimedia`
- `src/mloader/resolver`: Registry and implementations of site-specific resolvers (e.g., Bandcamp)
- `src/mloader/models`: Core data models and exceptions

## Project Management

### Installation
```bash
# Create virtual environment
python -m venv mloader_venv
source mloader_venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt
pip install -e .
```

### Running the Application
```bash
python src/mloader/__main__.py
```

### Testing
The project uses `pytest` for unit and integration tests.
```bash
pytest tests/
```

### Code Quality
We use `ruff` for linting and formatting to ensure a consistent codebase.
```bash
ruff check .
ruff format .
```

## Development Notes
- **Resolvers**: To add a new site, create a new resolver class inheriting from `SourceResolver` and register it in `DownloaderService`.
- **Threading**: Long-running tasks (downloading, resolving) are handled by `QThread` workers to keep the UI responsive.
