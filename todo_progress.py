#!/usr/bin/env python
"""
Parse the git history of TODO.txt and plot the number of items
in each section over time.

Usage:
    uv run python todo_progress.py
"""

import re
import subprocess
from datetime import datetime

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

SECTIONS = ["IN PROGRESS", "STILL TODO", "MAYBE TODO", "DONE", "NOT DONE"]

# Colorblind-friendly palette (blue, orange, purple, brown, pink)
# Avoids red-green distinction entirely.
COLORS = {
    "IN PROGRESS": "#0072B2",  # blue
    "STILL TODO": "#E69F00",  # orange
    "MAYBE TODO": "#CC79A7",  # pink
    "DONE": "#56B4E9",  # sky blue
    "NOT DONE": "#8C564B",  # brown
}

LINESTYLES = {
    "IN PROGRESS": "-",
    "STILL TODO": "-",
    "MAYBE TODO": "--",
    "DONE": "-",
    "NOT DONE": "--",
}

MARKERS = {
    "IN PROGRESS": "o",
    "STILL TODO": "s",
    "MAYBE TODO": "^",
    "DONE": "D",
    "NOT DONE": "x",
}


def count_items_per_section(text: str) -> dict[str, int]:
    """Count asterisk-prefixed items in each section of TODO.txt."""
    counts: dict[str, int] = {s: 0 for s in SECTIONS}
    current_section = None

    for line in text.splitlines():
        # Check if this line is a section header
        for section in SECTIONS:
            if re.match(rf"^{re.escape(section)}\s*:", line):
                current_section = section
                break
        else:
            # Count items (lines starting with *)
            if current_section and re.match(r"^\*\s", line):
                counts[current_section] += 1

    return counts


def get_todo_history() -> list[tuple[datetime, dict[str, int]]]:
    """Walk git history of TODO.txt and count items at each commit."""
    # Get all commits that touched TODO.txt, oldest first
    result = subprocess.run(
        ["git", "log", "--follow", "--format=%H %aI", "TODO.txt"],
        capture_output=True,
        text=True,
        check=True,
    )

    history = []
    lines = result.stdout.strip().splitlines()
    lines.reverse()  # oldest first (--reverse doesn't work with --follow)
    for line in lines:
        commit_hash, date_str = line.split(" ", 1)
        date = datetime.fromisoformat(date_str)

        # Get file content at this commit
        try:
            content = subprocess.run(
                ["git", "show", f"{commit_hash}:TODO.txt"],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError:
            # File might have had a different name in early history
            continue

        counts = count_items_per_section(content.stdout)
        history.append((date, counts))

    return history


def plot_progress(history: list[tuple[datetime, dict[str, int]]]) -> None:
    """Plot the item counts over time."""
    dates = [mdates.date2num(h[0]) for h in history]

    fig, ax = plt.subplots(figsize=(14, 7))

    for section in SECTIONS:
        values = [h[1][section] for h in history]
        ax.plot(
            dates,
            values,
            label=section,
            color=COLORS[section],
            linestyle=LINESTYLES[section],
            marker=MARKERS[section],
            markersize=3,
            markevery=max(1, len(dates) // 20),  # ~20 markers max
            linewidth=1.5,
        )

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.set_xlabel("Date")
    ax.set_ylabel("Number of items")
    ax.set_title("TODO.txt Progress Over Time")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()

    output_path = "todo_progress.png"
    fig.savefig(output_path, dpi=150)
    print(f"Saved to {output_path}")
    plt.show()


def main() -> None:
    print("Reading git history of TODO.txt ...")
    history = get_todo_history()
    print(f"Found {len(history)} commits.")

    if not history:
        print("No history found!")
        return

    # Show current state
    latest = history[-1][1]
    print("Current counts:")
    for section in SECTIONS:
        print(f"  {section}: {latest[section]}")

    plot_progress(history)


if __name__ == "__main__":
    main()
