"""Only changed backends need product smoke tests; unknown changes test both."""

import json
import os
import subprocess
from pathlib import Path


def select(paths):
    if not paths:
        return {"dos": True, "juku": True}
    result = {"dos": False, "juku": False}
    for path in paths:
        if path.endswith(".md") or path in {"LICENSE", ".gitignore"}:
            continue
        if path.startswith(("src/ravi/backends/dos/", "src/ravi/protocols/dos_v1")):
            result["dos"] = True
        elif path.startswith(
            (
                "src/ravi/backends/juku/",
                "src/ravi/backends/monitor",
                "src/ravi/protocols/monitor_v2",
                "src/ravi/monitor",
                "src/ravi/testing/monitor",
                "examples/memory_monitor",
            )
        ):
            result["juku"] = True
        else:
            return {"dos": True, "juku": True}
    return result


def main():
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        name = os.environ["GITHUB_EVENT_NAME"]
        if name == "pull_request":
            pr = event["pull_request"]
            revisions = [pr["base"]["sha"] + "..." + pr["head"]["sha"]]
        elif name == "push":
            revisions = [event["before"], event["after"]]
        else:
            revisions = []
        paths = (
            subprocess.check_output(
                ["git", "diff", "--name-only", "--no-renames", *revisions, "--"],
                text=True,
            ).splitlines()
            if revisions
            else []
        )
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError):
        paths = []
    chosen = select(paths)
    print(json.dumps(chosen))
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        for name, enabled in chosen.items():
            output.write(f"{name}={str(enabled).lower()}\n")


if __name__ == "__main__":
    main()
