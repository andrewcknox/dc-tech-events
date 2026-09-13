"""Check every source in sources.yaml: reachable? feed available? JavaScript needed?

Usage:  uv run python scripts/probe_sources.py [--out probe_report.md]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dte.probe import probe_all, render_markdown  # noqa: E402

if __name__ == "__main__":
    out = None
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
    results = probe_all()
    md = render_markdown(results)
    print(md)
    if out:
        out.write_text("# Source probe report\n\n" + md + "\n", encoding="utf-8")
        print(f"\nwritten to {out}")
