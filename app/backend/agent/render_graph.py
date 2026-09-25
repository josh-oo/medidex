#!/usr/bin/env python3
"""Render the LangGraph diagram to a PNG using Mermaid.ink."""
from __future__ import annotations

from pathlib import Path
import sys

from langchain_core.runnables.graph import MermaidDrawMethod

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.main import GRAPH  # noqa: E402


def main() -> None:
    output_path = Path(__file__).resolve().parent / "graph.png"
    mermaid_path = Path(__file__).resolve().parent / "graph.mmd"
    mermaid_text = GRAPH.get_graph().draw_mermaid()
    mermaid_path.write_text(mermaid_text, encoding="utf-8")
    png_bytes = GRAPH.get_graph().draw_mermaid_png(draw_method=MermaidDrawMethod.API)
    output_path.write_bytes(png_bytes)
    print(f"Wrote graph image to {output_path}")
    print(f"Wrote Mermaid source to {mermaid_path}")


if __name__ == "__main__":
    main()
