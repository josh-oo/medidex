"""Durations as a study keeps them: text such as "12 weeks", in a unit of `duration_units` of config/study.yaml."""

from __future__ import annotations

import re
from typing import Optional, Sequence

from .studyconfig import DurationUnitConfig, STUDY_CONFIG


class Durations:
    TEXT = re.compile(r"(\d+(?:\.\d+)?)\s+(\w+?)s?")

    def __init__(self, units: Optional[Sequence[DurationUnitConfig]] = None):
        self.units = list(STUDY_CONFIG.duration_units if units is None else units)  # largest first

    def format(self, seconds: float) -> str:
        """The duration in the largest unit that divides it evenly ("12 weeks"), or in seconds."""
        seconds = int(seconds)
        for unit in self.units:
            if seconds >= unit.seconds and seconds % unit.seconds == 0:
                amount = seconds // unit.seconds
                return f"{amount} {unit.name}{'' if amount == 1 else 's'}"
        return f"{seconds} s"

    def seconds(self, text: Optional[str]) -> Optional[float]:
        """The seconds of a text such as "12 weeks"; None if the text is no duration in a unit of the config."""
        match = self.TEXT.fullmatch((text or "").strip())
        by_name = {unit.name: unit.seconds for unit in self.units}
        return float(match[1]) * by_name[match[2]] if match and match[2] in by_name else None

    def normalize(self, text: Optional[str]) -> Optional[str]:
        """The text as "12 weeks" (the unit in the plural); None if it is no duration in a unit of the config."""
        match = self.TEXT.fullmatch((text or "").strip())
        return f"{match[1]} {match[2]}s" if match and self.seconds(text) is not None else None
