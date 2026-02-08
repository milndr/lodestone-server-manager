# Lodestone Server Manager

A Minecraft server manager in the terminal.

## Usage

Before running :

Make sure you have uv installed on your system, then
```bash
uv sync
```

to run the app :

### CLI
```bash
uv run lodestone
```
or
```bash
make cli
```

### TUI
```bash
uv run lodestone --tui
```
or
```bash
make tui
```

## Structure
- `lodestone/core`: Server and jar management
- `lodestone/ui`: CLI and TUI
- `lodestone/utils`: Helper functions.
