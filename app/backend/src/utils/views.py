"""The groups of a stored view (`views` of config/study.yaml with a `column`) as the study keeps them: JSON, a list
of groups, each group naming its parts. A part holds the ids of its tags:

    comparison: [{"intervention": [3000001, 3000002], "control": [3000113]}, ...]

or, if the part keeps values of fields next to its tags (`fields` of the part), an object:

    [{"intervention": {"tags": [3000001], "duration": "5 days"}, "control": {"tags": [3000113], "duration": "10 days"}}]

Creating a study also accepts names instead of ids. Older studies hold a plain text in the column, which is
no structure and is shown as it is."""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from .studyconfig import StudyViewConfig

Item = Union[int, str]


@dataclass
class StoredPart:
    tags: List[Item] = field(default_factory=list)  # ids (or, in a payload, names)
    values: Dict[str, str] = field(default_factory=dict)  # values of the part's `fields`


StoredGroup = Dict[str, StoredPart]


class StoredView:
    def __init__(self, config: StudyViewConfig):
        self.config = config

    def parse(self, raw: Optional[str]) -> Optional[List[StoredGroup]]:
        """The groups of the stored value, or None if it is empty or no structure (a plain text)."""
        if not raw or not raw.strip().startswith("["):
            return None
        try:
            data = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(data, list) or not all(isinstance(group, dict) for group in data):
            return None
        groups: List[StoredGroup] = []
        for entry in data:
            group: StoredGroup = {}
            for key, part in self.config.parts.items():
                parsed = self._part(entry.get(key), part.fields)
                if parsed is None:
                    return None
                group[key] = parsed
            if any(part.tags for part in group.values()):
                groups.append(group)
        return groups

    @staticmethod
    def _part(value, fields: List[str]) -> Optional[StoredPart]:
        if value is None:
            return StoredPart()
        tags, values = value, {}
        if isinstance(value, dict):
            tags = value.get("tags") or []
            values = {key: str(value[key]) for key in fields if value.get(key) not in (None, "")}
        if not isinstance(tags, list) or not all(isinstance(item, (int, str)) and not isinstance(item, bool) for item in tags):
            return None
        return StoredPart([item.strip() if isinstance(item, str) else item for item in tags if item != ""], values)

    def dumps(self, groups: List[StoredGroup]) -> Optional[str]:
        stored = []
        for group in groups:
            entry = {}
            for key, part in self.config.parts.items():
                content = group.get(key, StoredPart())
                entry[key] = {"tags": content.tags, **content.values} if part.fields else content.tags
            stored.append(entry)
        return json.dumps(stored) if stored else None
