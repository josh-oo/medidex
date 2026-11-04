"""Extension point for storage a deployable keeps outside the tables of the resource database (e.g. chat histories
in a database of their own), counted by GET /databases/{id}/storage as storage of the updates of a database: what
their curation leaves behind, which goes once they are done. Tables of the resource database are counted by
themselves (DatabaseRepository.get_table_storage); downstream deployables register the rest at startup.

When a report of an update is merged or deleted (UpdateMergeService), every storage hands in what it keeps of the
report for the archive of the report (ReportArchive.data, under its `key`) and then removes it.
"""

from typing import Any, Dict, List, Protocol, Sequence


class UpdateStorage(Protocol):
    # What it holds, as the storage of a database shows it (e.g. "AI history").
    label: str
    # Its section in the archive of a report (e.g. "ai_history").
    key: str

    async def measure(self, report_ids: Sequence[int]) -> int:
        """The bytes kept for the given reports (those the updates of one database brought in)."""
        ...

    async def archive(self, report_ids: Sequence[int]) -> Dict[int, Any]:
        """What is kept for each of the reports, as JSON, to archive; reports without anything may be left out."""
        ...

    async def purge(self, report_ids: Sequence[int]) -> None:
        """Removes what is kept for the reports, once they are archived."""
        ...


class UpdateStorageRegistry:
    def __init__(self) -> None:
        self._storages: List[UpdateStorage] = []

    def register(self, storage: UpdateStorage) -> None:
        self._storages.append(storage)

    def all(self) -> List[UpdateStorage]:
        return list(self._storages)


update_storage_registry = UpdateStorageRegistry()
