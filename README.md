# QR Code Labels

[![Copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border-orange.json)](https://github.com/copier-org/copier)

This tool creates printable QR code labels to help you track your belongings efficiently.

The generator creates unique 5-character alphanumeric codes (excluding 'Q') and tiles them onto LETTER-sized paper for easy printing.

## Features

- **CLI Interface**: Command-line tool with flexible options.
- **SVG Generation**: Creates high-quality vector graphics for labels.
- **PDF Export**: Consolidates labels into a printable PDF format.
- **Customizable Layout**: Support for scaling, repeating codes, grouping, and adding cut lines.
- **Inventory Ready**: Designed for smart home inventory or moving boxes.

## Requirements

- **Python**: version 3.13 or higher.
- **uv**: A fast Python package manager.

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for package management.

```bash
# Clone the repository
git clone https://github.com/turkoid/qr-code-labels.git
cd qr-code-labels

# Install dependencies
uv sync
```

## Usage

You can run the tool using `uv run qr` or by installing it.

### Commands

```bash
# Basic usage: Generate 10 unique labels, each repeated twice
uv run qr -c 10 -r 2

# Using the SPEC argument (count[xrepeat][@scale])
uv run qr 5x3@1.5
```

### Options

- `-c, --count INTEGER`: Number of unique codes to generate (default: 1).
- `-r, --repeat INTEGER`: Number of copies for each code (default: 1).
- `-s, --scale FLOAT`: Scale factor (base = 1 inch, default: 1.5).
- `-o, --output PATH`: Output directory for generated files.
- `-n, --name TEXT`: Base name for the generated files.
- `--group`: Group identical codes together (useful with cut lines).
- `--fill`: If grouped, repeat codes until the row is filled.
- `-x, --include-cut-lines`: Draw dotted lines for easy cutting.
- `--save-svgs`: Save intermediate SVG files in an `svgs` directory.
- `--save-codes`: Save the generated codes to a text file.

## Project Structure

```text
.
├── src/qr_code_labels/
│   ├── main.py       # Core logic and CLI definition
│   └── __init__.py
├── pyproject.toml    # Project metadata and dependencies
├── uv.lock           # Dependency lock file
└── LICENSE           # MIT License
```

## Development

### Scripts
- **Pre-commit**: The project uses `pre-commit` for code quality. Run `uv run pre-commit install` to set it up.
- **Linting**: Uses `ruff` for linting and formatting.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## The Future

- Support for more paper sizes and types including label paper