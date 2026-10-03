import json
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

DATA_FILE = Path(__file__).with_name("changelog_data.json")


class ChangelogEntry(BaseModel):
    """One month of work, as the repository records it.

    This used to be a hardcoded list claiming releases from 2024-12-01 to
    2025-04-20 -- eight months before the first commit -- with specifics
    no commit backs up. Every line now comes from a real commit subject;
    see utils/build_changelog.py, which regenerates the data file.

    There are no tags in this repository, so there is nothing to call a
    version. Entries are identified by the month instead.
    """

    period: str = Field(..., description="The month the work landed in, YYYY-MM.")
    date: str = Field(..., description="First day of that month, for display.")
    new_features: List[str] = []
    improvements: List[str] = []
    bugfixes: List[str] = []
    tags: List[str] = []
    other_changes: int = Field(
        0,
        description=(
            "Commits in that month with nothing to say to a reader of the "
            "changelog -- chores, docs, tests, CI."
        ),
    )
    version: Optional[str] = Field(
        None, description="Unused: this project is not tagged."
    )


@lru_cache(maxsize=1)
def _entries() -> List[ChangelogEntry]:
    """Read once. The file is generated at development time and committed."""
    if not DATA_FILE.exists():
        return []
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return [ChangelogEntry(**item) for item in raw]


router_changelog = APIRouter(
    prefix="/api/changelog",
    tags=["changelog"],
    default_response_class=JSONResponse,
)


@router_changelog.get(
    "",
    response_model=List[ChangelogEntry],
    summary="Get changelog",
    description=(
        "Months of work, newest first, built from the repository's commit "
        "history rather than written by hand."
    ),
)
async def get_changelog() -> List[ChangelogEntry]:
    return _entries()
