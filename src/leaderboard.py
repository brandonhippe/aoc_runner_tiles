import re
from dataclasses import dataclass
from typing import Dict, Optional, Union

from aoc_runner.data_tracker import DataTracker
from aoc_runner.web import get_leaderboard


@dataclass
class DayScores:
    time1: Union[str, None] = None
    rank1: Union[str, None] = None
    score1: Union[str, None] = None
    time2: Union[str, None] = None
    rank2: Union[str, None] = None
    score2: Union[str, None] = None


def parse_leaderboard(year: int, runtime_data: Optional[DataTracker]=None, use_runtime: bool=False) -> Dict[int, DayScores]:
    if use_runtime:
        if runtime_data is None:
            raise ValueError("Runtime data must be provided if use_runtime is True.")

    no_stars = "You haven't collected any stars... yet."
    if year < 2025:
        start = '<span class="leaderboard-daydesc-both"> *Time *Rank *Score</span>\n'
    else:
        start = '<span class="leaderboard-daydesc-both">-Part 2-</span>\n'
    end = "</pre>"
    html = get_leaderboard(year)
    if no_stars in html:
        return {}
    matches = re.findall(rf"{start}(.*?){end}", html, re.DOTALL | re.MULTILINE)
    assert len(matches) > 0, "Found no leaderboard?!"
    table_rows = matches[0].strip().split("\n")
    day_to_scores = {}
    for line in table_rows:
        day, *scores = re.split(r"\s+", line.strip())
        # replace "-" with None to be able to handle the data later, like if no score existed for the day
        scores = [s if s != "-" else None for s in scores]
        if year >= 2025:
            scores.insert(1, None)
            scores.insert(1, None)
            if len(scores) > 3:
                scores.insert(4, None)
                scores.insert(4, None)
        
        assert len(scores) in (3, 6), f"Number scores for {day=} ({scores}) are not 3 or 6."
        if use_runtime:
            try:
                scores[0] = f"{runtime_data[year, int(day), 1]:.3f}"
            except KeyError:
                scores[0] = None
            try:
                scores[3] = f"{runtime_data[year, int(day), 2]:.3f}"
            except KeyError:
                scores[3] = None

        day_to_scores[int(day)] = DayScores(*scores)
    return day_to_scores
