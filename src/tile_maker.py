import argparse
import datetime
import itertools
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from PIL import ImageColor

from ....data_tracker import DataTracker
from ....Languages import Language
from ....web import AOC_COOKIE
from .colors import language_to_colors
from .drawer import TileDrawer
from .html import HTML
from .leaderboard import DayScores, parse_leaderboard


@dataclass
class YearData:
    day_to_scores: Dict[int, DayScores]
    day_to_paths: Dict[int, List[Language]]
    day_to_stars: Dict[int, int]


@dataclass
class SolveData:
    year_to_data: Dict[int, YearData]


class TileMaker:
    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser) -> None:
        """
        Add arguments to the parser. Must be a static method
        """
        parser.add_argument(
            "--aoc-tiles-dir",
            type=str,
            default=Path(os.getcwd(), ".tiles"),
            help="Directory to store the tiles in. Default: .tiles",
        )

        parser.add_argument(
            "--running-lock-path",
            type=str,
            default=Path(os.getcwd(), ".tiles", "running.lock"),
            help="Path to the running lock file. Default: .tiles/running.lock",
        )

        parser.add_argument(
            "--image-dir",
            type=str,
            default=Path(os.getcwd(), ".tiles", "images"),
            help="Directory to store the images in. Default: .tiles/images",
        )

        parser.add_argument(
            "--cache-dir",
            type=str,
            default=Path(os.getcwd(), "__cache__"),
            help="Directory to store the cache in. Default: __cache__",
        )

        parser.add_argument(
            "--what-to-show-on-right-side",
            type=str,
            default="auto",
            choices=["auto", "checkmark", "time_and_rank", "runtime"],
            help="What information to display on the right side of each tile. "
                 "'checkmark' only displays a checkmark for each part if the day is solved. "
                 "'time_and_rank' displays the time and rank on the global leaderboard (requires session.cookie). "
                 "'runtime' displays the runtime for the solution. "
                 "'auto' will use 'time_and_rank' if session.cookie exists, otherwise 'checkmark'.",
        )
        
        parser.add_argument(
            "--count-as-solved-when",
            type=str,
            default="auto",
            choices=["auto", "on_leaderboard", "file_exists", "either", "both"],
            help="Condition to count a task as solved. Note that 'on_leaderboard', 'either' and 'both' require a "
                 "session cookie. 'auto' will use 'both' if session.cookie exists, otherwise 'file_exists'.",
        )
        
        parser.add_argument(
            "--create-all-days",
            action="store_true",
            help="Whether to create entries for all days upfront. "
                 "If this is not set, only days with solutions will be created.",
        )

        parser.add_argument(
            "--show-total-stars-for-all-years",
            type=str,
            default="auto",
            choices=["no", "auto", "yes"],
            help="Whether to add an additional header in front which shows the total collected stars for all years. "
                 "'auto' will only show the header if you have stars in at least 3 separate years. "
                 "'yes' will always show the header. 'no' will never show the header.",
        )

        parser.add_argument(
            "--contrast-improvement-type",
            type=str,
            default="dark",
            choices=["none", "outline", "dark"],
            help="Some languages have very light colors and are hard to see with a white font. Here you can choose "
                 "how the text color changes when the background is too light. 'dark' makes the font dark, "
                 "'outline' adds a black outline.",
        )
        
        parser.add_argument(
            "--contrast-improvement-threshold",
            type=int,
            default=30,
            choices=range(0, 256),
            help="The threshold for the contrast improvement feature (between 0 and 255). ",
        )

        parser.add_argument(
            "--outline-color",
            type=str,
            default="#6C6A6A",
            help="Color used for outlining elements. "
        )

        parser.add_argument(
            "--not-completed-color",
            type=str,
            default="#333333",
            help="Color to signify incomplete tasks. ",
        )

        parser.add_argument(
            "--top100-color",
            type=str,
            default="#ffdd00",
            help="Color to highlight top 100 ranking. Only used if session cookie is provided.",
        )

        parser.add_argument(
            "--text-color",
            type=str,
            default="#FFFFFF",
            help="Text color. ",
        )
        
        parser.add_argument(
            "--tile-width-px",
            type=str,
            default="161px",
            help="Width of tiles in pixels. You likely don't need to change this.",
        )

    def __init__(self, **kwargs):
        vars(self).update(kwargs)
        
        if self.count_as_solved_when == "auto":
            self.count_as_solved_when = "both" if AOC_COOKIE else "file_exists"

        if self.what_to_show_on_right_side == "auto":
            self.what_to_show_on_right_side = "time_and_rank" if AOC_COOKIE else "checkmark"

        for argname, argval in filter(lambda i: "color" in i[0] and isinstance(i[1], str), vars(self).items()):
            vars(self)[argname] = ImageColor.getrgb(argval)

        self.tile_drawer = TileDrawer(self)

    def print(self, *args, **kwargs):
        if self.verbose:
            print("Tiles: ", *args, **kwargs)

    def __call__(self, *args, **kwargs) -> str:
        self._ensure_is_not_running_already()
        self.print("Running AoC-Tiles")
        solve_data = self.compose_solve_data(**kwargs)
        html = HTML()
        self._add_total_completed_stars_to_html(solve_data, html)

        for year, data in sorted(solve_data.year_to_data.items(), reverse=True):
            self.handle_year(year, data, html, kwargs.get("readme_path", Path(os.getcwd(), "README.md")))

        return str(html)

        # if self.auto_add_tiles_to_git in ["add", "amend"]:
        #     self.solution_finder.git_add(self.image_dir)
        #     self.solution_finder.git_add(self.readme_path)

        # if self.auto_add_tiles_to_git in ["amend"]:
        #     try:
        #         with open(self.running_lock_path, "w") as file:
        #             file.write("")
        #         self.solution_finder.git_commit_amend()
        #     finally:
        #         # print("Could not amend commit. Maybe there is nothing to amend?")
        #         if self.running_lock_path.exists():
        #             self.running_lock_path.unlink()

    def _get_stars(self, solved: Optional[DayScores], solution: Optional[DataTracker]) -> int:
        on_leaderboard = 0 if solved is None else bool(solved.rank1) + bool(solved.rank2)
        file_exists = 0 if solution is None else len(solution)
        return {
            "on_leaderboard": on_leaderboard,
            "file_exists": file_exists,
            "either": max(on_leaderboard, file_exists),
            "both": min(on_leaderboard, file_exists),
        }[self.count_as_solved_when]

    def compose_solve_data(self, solutions_by_year: Optional[DataTracker]=None, languages: List[Language]=[], years: List[int]=[], **kwargs) -> SolveData:
        is_leaderboard_needed = self.what_to_show_on_right_side in [
            "time_and_rank", "runtime"
        ] or self.count_as_solved_when in ["on_leaderboard", "both", "either"]

        solve_data = SolveData({})

        for language, year in itertools.product(languages, years):
            if year not in solutions_by_year:
                continue

            day_to_solution = solutions_by_year[year]
            if language in day_to_solution:
                day_to_solution = day_to_solution[language]
            day_to_scores = solve_data.year_to_data[year].day_to_scores if year in solve_data.year_to_data else {}
            if is_leaderboard_needed:
                day_to_scores = parse_leaderboard(year, use_runtime=self.what_to_show_on_right_side == "runtime", runtime_data=solutions_by_year)

            day_to_stars = solve_data.year_to_data[year].day_to_stars if year in solve_data.year_to_data else {}
            day_to_paths = solve_data.year_to_data[year].day_to_paths if year in solve_data.year_to_data else defaultdict(list)

            for day in filter(lambda d: (year, d) in language.ran, range(1, 26)):
                stars = self._get_stars(day_to_scores.get(day), day_to_solution[day])
                if day == 25 and stars == 1:
                    stars = 2

                day_to_stars[day] = stars
                day_to_paths[day].append(language)

            solve_data.year_to_data[year] = YearData(day_to_scores, day_to_paths, day_to_stars)
        
        return solve_data

    def handle_day(
            self,
            day: int,
            year: int,
            solutions: List[Language],
            day_scores: Optional[DayScores],
            needs_update: bool,
            stars: int,
            readme_path: Path
    ):
        languages = []
        for solution in solutions:
            lang = solution.lang.title()
            if lang in language_to_colors() and lang not in languages:
                languages.append(lang)
        
        solution_link = solutions[0].code_file(year, day).relative_to(readme_path.parent) if solutions else None
        day_graphic_path = self.image_dir / f"{year:04}/{day:02}.png"
        day_graphic_path.parent.mkdir(parents=True, exist_ok=True)
        if not day_graphic_path.exists() or needs_update:
            self.tile_drawer.draw_tile(f"{day:02}", languages, day_scores, day_graphic_path, stars=stars)
        
        return day_graphic_path.relative_to(readme_path.parent), solution_link

    def fill_empty_days_in_dict(self, day_to_solutions: Dict[int, List[Path]], max_day) -> None:
        if not self.create_all_days and len(day_to_solutions) == 0:
            self.print(f"Current year has no solutions!")
        for day in range(1, max_day + 1):
            if day not in day_to_solutions:
                day_to_solutions[day] = []

    def _get_programming_languages_used_daily(self, year_data: YearData) -> List[str]:
        languages = None
        for paths in year_data.day_to_paths.values():
            suffixes = {path.lang.title() for path in paths}
            if languages is None:
                languages = suffixes
            languages &= suffixes

        return list(languages) if languages else []

    def handle_year(self, year: int, year_data: YearData, html: HTML, readme_path: Path):
        self.print(f"=== Generating table for year {year} ===")
        leaderboard = year_data.day_to_scores
        day_to_solutions = year_data.day_to_paths
        with html.tag("h1", align="center"):
            stars = sum(year_data.day_to_stars.values())
            daily_language = " - " + "/".join(self._get_programming_languages_used_daily(year_data))
            html.push(f"{year} - {stars} ⭐{daily_language}")
        max_solved_day = max((day for day, stars in year_data.day_to_stars.items() if stars > 0), default=0)
        max_day = 25 if self.create_all_days else max_solved_day
        self.fill_empty_days_in_dict(day_to_solutions, max_day)

        for day in range(1, max_day + 1):
            solutions = day_to_solutions.get(day, [])
            stars = year_data.day_to_stars[day]
            tile_path, solution_path = self.handle_day(day, year, solutions, leaderboard.get(day), True, stars=stars, readme_path=readme_path)

            if solution_path is None:
                solution_href = str(solution_path)
            else:
                solution_href = str(solution_path.as_posix())

            with html.tag("a", href=solution_href):
                html.tag("img", closing=False, src=tile_path.as_posix(), width=self.tile_width_px)

    def _ensure_is_not_running_already(self):
        if self.aoc_tiles_dir.exists():
            if self.running_lock_path in self.aoc_tiles_dir.iterdir():
                self.print("AoC-Tiles is already running! Remove running.lock if this is not the case.")
                exit()

    def _add_total_completed_stars_to_html(self, solve_data: SolveData, html: HTML):
        add_header = self.show_total_stars_for_all_years == 'yes' \
                     or self.show_total_stars_for_all_years == 'auto' and len(solve_data.year_to_data) >= 3
        if add_header:
            total_stars = sum(sum(data.day_to_stars.values()) for data in solve_data.year_to_data.values())
            total_possible_stars = self._get_total_possible_stars_for_date(datetime.datetime.now(datetime.timezone.utc))
            with html.tag("h1", align="center"):
                html.push(f"Advent of Code - {total_stars}/{total_possible_stars} ⭐")
