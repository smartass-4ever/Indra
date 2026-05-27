"""Indra CLI."""

import os
import sys


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        print(
            "Indra — web intelligence that only thinks when the web changes.\n\n"
            "Usage:\n"
            "  indra demo           Run the competitor monitor demo\n"
            "  indra watch <url>    Watch a single URL\n"
            "  indra reset          Clear the demo snapshot DB (fresh start)\n"
        )
        return

    cmd = sys.argv[1]

    if cmd == "demo":
        from indra.demo import run_demo
        run_demo()

    elif cmd == "reset":
        import glob as _glob
        removed = []
        for f in _glob.glob("indra*.db") + _glob.glob("indra*.db-wal") + _glob.glob("indra*.db-shm"):
            try:
                os.remove(f)
                removed.append(f)
            except OSError as e:
                print(f"Could not remove {f}: {e}")
        if removed:
            print(f"Cleared: {', '.join(removed)}")
        else:
            print("Nothing to clear (no indra*.db files found).")

    elif cmd == "watch" and len(sys.argv) >= 3:
        url = sys.argv[2]
        api_key = os.environ.get("BRIGHTDATA_API_KEY", "")
        if not api_key:
            print("Error: set BRIGHTDATA_API_KEY env var first.")
            sys.exit(1)
        import indra
        agent  = indra.init(brightdata_api_key=api_key)
        result = agent.watch(url, question="What is the key content on this page?")
        print(f"Changed : {result.changed}")
        print(f"Summary : {result.summary}")
        if result.insight:
            print(f"Insight : {result.insight[:300]}")
        agent.print_stats()
        agent.close()

    else:
        print(f"Unknown command: {cmd}. Run 'indra --help'.")
