"""
Build the changelog the API serves from the repository's own history.

It used to be a hardcoded list in src/api/changelog.py claiming releases
from 2024-12-01 to 2025-04-20 -- eight months before the first commit
(2025-07-30) -- with specifics like "Home page loads 20% faster with
optimised HLS prefetch" that no commit backs up. Every line here is the
subject of a real commit instead.

There are no tags in this repository, so there are no versions to list.
Entries are grouped by the month the work landed in, newest first.

Only commits written in conventional form are listed, because only those
say what kind of change they are:

    feat:     -> New Features
    fix:      -> Bug Fixes
    refactor: -> Improvements
    perf:     -> Improvements

Everything else (chore, docs, test, ci, build, and commits with no type)
is counted but not listed -- a changelog is for people reading about the
product, and "bump a dependency" is not that.

Run it where git is available; the container has no repository. The
generated file is committed, and the API reads it.

    python -m utils.build_changelog            # writes the JSON
    python -m utils.build_changelog --check    # fails if it is stale
"""

import argparse
import json
import re
import subprocess
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

OUTPUT = Path(__file__).resolve().parent.parent / "src" / "api" / "changelog_data.json"

#: "feat(scope): subject" / "fix: subject"
COMMIT = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?: (?P<subject>.+)$")

SECTIONS = {
    "feat": "new_features",
    "fix": "bugfixes",
    "refactor": "improvements",
    "perf": "improvements",
}

TAG_FOR = {
    "new_features": "New Features",
    "improvements": "Improvements",
    "bugfixes": "Bug Fixes",
}


def _git_log() -> List[str]:
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "log", "--no-merges", "--date=short", "--format=%ad%x1f%s"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def _subject(match: "re.Match[str]") -> str:
    """The commit subject, with the scope kept as a prefix when it says where.

    `fix(player): ...` reads better as "Player: ..." than as the bare
    subject, and the scope is the only thing saying which part changed.
    """
    subject = match.group("subject").strip()
    # Commit subjects are written lower-case; a sentence is not.
    subject = subject[:1].upper() + subject[1:]
    scope = match.group("scope")
    if scope:
        return f"{scope}: {subject}"
    return subject


@dataclass
class _Month:
    """One month's worth of listed changes."""

    period: str
    new_features: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    bugfixes: List[str] = field(default_factory=list)
    other_changes: int = 0

    def add(self, section: str, text: str) -> None:
        bucket: List[str] = getattr(self, section)
        if text not in bucket:
            bucket.append(text)

    def as_entry(self) -> Dict[str, object]:
        return {
            "period": self.period,
            "date": f"{self.period}-01",
            "new_features": self.new_features,
            "improvements": self.improvements,
            "bugfixes": self.bugfixes,
            # A month with nothing worth listing is still a month of work;
            # the count says so without printing an empty card.
            "other_changes": self.other_changes,
            "tags": [
                TAG_FOR[key]
                for key in ("new_features", "improvements", "bugfixes")
                if getattr(self, key)
            ],
        }


def build() -> List[Dict[str, object]]:
    months: "OrderedDict[str, _Month]" = OrderedDict()

    for line in _git_log():
        date, _, message = line.partition("")
        period = date[:7]  # YYYY-MM
        month = months.setdefault(period, _Month(period=period))

        match = COMMIT.match(message.strip())
        section = SECTIONS.get(match.group("type")) if match else None
        if match and section:
            month.add(section, _subject(match))
        else:
            month.other_changes += 1

    return [month.as_entry() for month in months.values()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed file does not match the history",
    )
    args = parser.parse_args()

    payload = json.dumps(build(), indent=2, ensure_ascii=False) + "\n"

    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != payload:
            print(
                f"{OUTPUT.name} is out of date -- run python -m utils.build_changelog"
            )
            sys.exit(1)
        print(f"{OUTPUT.name} is up to date")
        return

    OUTPUT.write_text(payload, encoding="utf-8")
    entries = json.loads(payload)
    listed = sum(
        len(e["new_features"]) + len(e["improvements"]) + len(e["bugfixes"])
        for e in entries
    )
    print(
        f"wrote {OUTPUT.relative_to(OUTPUT.parents[2])}: {len(entries)} months, {listed} entries"
    )


if __name__ == "__main__":
    main()
