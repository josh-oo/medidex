"""Extension point for what a deployable does with a report of an update when it is merged into the core database (e.g.
applying the changes its curators proposed to the studies it is linked to). Downstream deployables register their hooks at
startup.

A hook runs inside the transaction of the merge (UpdateMergeService), once the report, the studies selected for it and its
links to them are in the core database (under the ids they had in the update) and before the report of the update is
removed, so it still reads its update data; it must not commit. An exception rolls the merge back.
"""

from typing import List, Optional, Protocol, Sequence

from sqlalchemy.ext.asyncio import AsyncSession


class MergeHook(Protocol):
    async def on_merge(self, db: AsyncSession, user_id: Optional[str], report_id: int, study_ids: Sequence[int]) -> None:
        """Called for a report being merged with the studies selected for it, on the session of the merge."""
        ...


class MergeHookRegistry:
    def __init__(self) -> None:
        self._hooks: List[MergeHook] = []

    def register(self, hook: MergeHook) -> None:
        self._hooks.append(hook)

    def all(self) -> List[MergeHook]:
        return list(self._hooks)


merge_hook_registry = MergeHookRegistry()
