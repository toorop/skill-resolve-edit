"""common.py: timecodes, rates, the reference map (Clips), short names, profile lookup."""
import os
import re
import unittest

from helpers import SETTINGS, TempDirTest, clips_data, write_json

import common
from common import Clips, ascii_only, fps_value, is_spoken, parse_time, short_from_pattern, short_name, tc


class Rates(unittest.TestCase):
    def test_fps_value_keeps_integral_rates_as_int(self):
        self.assertIs(type(fps_value(25.0)), int)
        self.assertEqual(fps_value("50"), 50)
        self.assertEqual(fps_value(29.97), 29.97)


class Timecodes(unittest.TestCase):
    def test_seconds_to_timecode(self):
        self.assertEqual(tc(0, 25), "00:00:00:00")
        self.assertEqual(tc(1.48, 25), "00:00:01:12")
        self.assertEqual(tc(3661.04, 25), "01:01:01:01")

    def test_frames_to_timecode(self):
        self.assertEqual(tc(24, 25, frames=True), "00:00:00:24")
        self.assertEqual(tc(25, 25, frames=True), "00:00:01:00")
        self.assertEqual(tc(49, 50, frames=True), "00:00:00:49")  # 50p counts 50 frames per second
        self.assertEqual(tc(50, 50, frames=True), "00:00:01:00")

    def test_fractional_rates_count_on_the_nominal_rate(self):
        # Resolve's non-drop-frame timecode: 29.97 counts 30 frames per "second", 23.976 counts 24
        self.assertEqual(tc(30, 29.97, frames=True), "00:00:01:00")
        self.assertEqual(tc(29, 29.97, frames=True), "00:00:00:29")
        self.assertEqual(tc(24, 23.976, frames=True), "00:00:01:00")

    def test_parse_time(self):
        self.assertEqual(parse_time(2.5), 2.5)
        self.assertAlmostEqual(parse_time("00:00:01:12", 25), 1.48)
        self.assertAlmostEqual(parse_time("01:00:00:00", 50), 3600.0)
        self.assertAlmostEqual(parse_time("00:00:01:00", 29.97), 30 / 29.97)

    def test_round_trip_frames(self):
        for fps in (25, 50, 23.976, 29.97, 59.94):
            for f in (0, 1, 23, 24, 29, 30, 1799, 107892):
                self.assertAlmostEqual(parse_time(tc(f, fps, frames=True), fps) * fps, f, places=6, msg=(fps, f))


class ReferenceMap(unittest.TestCase):
    def setUp(self):
        # A (25p, 4 s), B (50p, 2 s = 50 timeline frames), C (25p, 1 s)
        self.clips = Clips(clips_data([("A0001.MP4", 100, 25, "A0001"), ("B_20260101_002.MP4", 50, 50, "B002"),
                                       ("A0003.MP4", 25, 25, "A0003")]))

    def test_rate_and_length(self):
        self.assertEqual(self.clips.fps, 25)
        self.assertEqual(self.clips.total_frames, 175)

    def test_boundaries_start_inclusive_end_exclusive(self):
        self.assertEqual(self.clips.at_frame(0), "A0001.MP4")
        self.assertEqual(self.clips.at_frame(99), "A0001.MP4")
        self.assertEqual(self.clips.at_frame(100), "B_20260101_002.MP4")
        self.assertEqual(self.clips.at_frame(174), "A0003.MP4")
        self.assertIsNone(self.clips.at_frame(175))
        self.assertEqual(self.clips.at(4.0), "B_20260101_002.MP4")

    def test_split_on_rush_boundaries(self):
        # offsets from the start of each rush, in timeline frames
        self.assertEqual(self.clips.split(90, 160), [["A0001.MP4", 90, 100], ["B_20260101_002.MP4", 0, 50],
                                                     ["A0003.MP4", 0, 10]])
        self.assertEqual(self.clips.split(10, 20), [["A0001.MP4", 10, 20]])
        self.assertEqual(self.clips.split(20, 20), [])

    def test_metadata(self):
        self.assertEqual(self.clips.short("B_20260101_002.MP4"), "B002")
        self.assertEqual(self.clips.file("A0001.MP4"), "A0001.MP4")
        self.assertEqual(self.clips.by_short("A0003"), ("A0003.MP4", 150, 175))
        with self.assertRaises(KeyError):
            self.clips.by_short("nope")

    def test_old_format_list(self):
        clips = Clips([["X_20260101_001.MP4", 0, 50], ["X_20260101_002.MP4", 50, 80]], settings={})
        self.assertEqual(clips.fps, 25)
        self.assertEqual(clips.short("X_20260101_002.MP4"), "X_20260101_002")
        self.assertEqual(clips.file("X_20260101_002.MP4"), "X_20260101_002.MP4")
        self.assertEqual(clips.total_frames, 80)


class ShortNames(unittest.TestCase):
    def test_groups_are_joined(self):
        self.assertEqual(short_from_pattern("B_20260101_042.MP4", re.compile(r"(B)_\d{8}_(\d{3})")), "B042")

    def test_whole_match_without_groups(self):
        self.assertEqual(short_from_pattern("clip_A0522.MP4", re.compile(r"A\d{4}")), "A0522")

    def test_profile_rules_then_file_stem(self):
        self.assertEqual(short_name("B_20260101_007.MP4", SETTINGS), "B007")
        self.assertEqual(short_name("holiday.mov", SETTINGS), "holiday")


class Text(unittest.TestCase):
    def test_ascii_only(self):
        self.assertEqual(ascii_only("Bêtisier à Noël"), "Betisier a Noel")

    def test_is_spoken(self):
        self.assertTrue(is_spoken({"type": "word", "text": "Hello"}))
        self.assertFalse(is_spoken({"type": "word", "text": "?"}))
        self.assertFalse(is_spoken({"type": "spacing", "text": " "}))
        self.assertFalse(is_spoken({"type": "audio_event", "text": "(laughs)"}))


class Profile(TempDirTest):
    def test_pointer_file_in_a_parent_folder(self):
        write_json(self.path("channel", "resolve-edit.json"), {"profile": "../profile"})
        video = self.path("channel", "video 1", "transcripts")
        os.makedirs(video)
        old = os.environ.pop(common.PROFILE_ENV, None)
        try:
            self.assertEqual(os.path.normcase(common.find_profile(video)), os.path.normcase(self.profile))
            os.environ[common.PROFILE_ENV] = self.path("elsewhere")
            self.assertEqual(common.find_profile(video), os.path.abspath(self.path("elsewhere")))
        finally:
            os.environ.pop(common.PROFILE_ENV, None)
            if old is not None:
                os.environ[common.PROFILE_ENV] = old

    def test_no_profile(self):
        old = os.environ.pop(common.PROFILE_ENV, None)
        try:
            self.assertEqual(common.load_settings(self.path("missing")), {})
        finally:
            if old is not None:
                os.environ[common.PROFILE_ENV] = old

    def test_jsonc_comments(self):
        p = self.path("s.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write('// comment\n{\n  // another\n  "a": 1\n}\n')
        self.assertEqual(common.load_jsonc(p), {"a": 1})


if __name__ == "__main__":
    unittest.main()
