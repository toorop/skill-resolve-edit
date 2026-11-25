"""edl_lib.compute_linear (the linear cut rules) and build_linear_edl.py.

All times are chosen so that seconds x 25 never fall on half a frame (rounding stays unambiguous)."""
import unittest

from helpers import TempDirTest, clips_data, read_json, transcript, write_json

from common import Clips
from edl_lib import compute_linear

FPS = 25


def words(*spec):
    """spec = (text, start, end), ... -> the word list the scripts read (no spacing tokens)."""
    return [{"text": t, "start": s, "end": e, "type": "word", "speaker_id": "speaker_0"} for t, s, e in spec]


def run(spec, rushes=(("A.MP4", 500),), decisions=None, settings=None):
    clips = Clips(clips_data([(n, l) for n, l in rushes]))
    return compute_linear(decisions or {}, words(*spec), clips, settings or {})


class Gaps(unittest.TestCase):
    SPEC = [("Hello", 1.02, 1.42), ("there.", 1.42, 1.82),
            ("Short", 3.22, 3.62),                      # 1.4 s gap: under gap_min (2 s), untouched
            ("pause", 3.62, 4.02),
            ("Long", 7.02, 7.42),                       # 3.0 s gap: shortened, 0.5 s of air kept on each side
            ("end.", 7.42, 7.82)]

    def test_long_gap_shortened_short_gap_kept_head_and_tail_trimmed(self):
        ref, cuts, demos, report = run(self.SPEC)
        # head: 1.02 - 0.3 = 0.72 s -> frame 18; gap cut 4.52..6.52 s -> 113..163; tail from 7.82 + 0.5 = 8.32 s -> 208
        self.assertEqual(ref, [[18, 113], [163, 208]])
        self.assertEqual([g[1] for g in report["gaps_shortened"]], [3.0])
        self.assertEqual(demos, [])
        self.assertEqual(len(report["heads_tails_trimmed"]), 2)

    def test_thresholds_come_from_the_profile_then_the_decisions(self):
        ref, _, _, report = run(self.SPEC, settings={"linear": {"gap_min": 1.0}})
        self.assertEqual(len(report["gaps_shortened"]), 2)          # the 1.4 s gap is now long
        ref, _, _, report = run(self.SPEC, settings={"linear": {"gap_min": 1.0}},
                                decisions={"linear": {"gap_min": 5.0}})
        self.assertEqual(report["gaps_shortened"], [])              # decisions.json wins
        self.assertEqual(ref, [[18, 208]])

    def test_demonstration_announced_keeps_the_gap(self):
        spec = [("Now", 1.02, 1.42), ("look", 1.42, 1.82), ("Done.", 5.02, 5.42)]
        ref, _, demos, report = run(spec, settings={"linear": {"demo_cues": ["look"]}})
        self.assertEqual(len(demos), 1)
        self.assertEqual(report["gaps_shortened"], [])
        self.assertEqual(ref, [[18, 148]])                          # 0.72 s .. 5.42 + 0.5 = 5.92 s

    def test_keep_head_and_keep_tail(self):
        ref, _, _, report = run(self.SPEC, decisions={"linear": {"keep_head": ["A"], "keep_tail": ["A"]}})
        self.assertEqual(ref, [[0, 113], [163, 500]])
        self.assertEqual(report["heads_tails_trimmed"], [])


class Removals(unittest.TestCase):
    def test_removed_range_in_seconds_or_timecode(self):
        spec = [("w%d" % k, round(1.02 + 0.4 * k, 2), round(1.38 + 0.4 * k, 2)) for k in range(20)]  # 1.02 .. 8.98
        dec = {"linear": {"remove": [{"label": "retake", "start": "00:00:03:00", "end": 5.0}]}}
        ref, cuts, _, report = run(spec, decisions=dec)
        self.assertEqual(ref, [[18, 75], [125, 237]])               # tail: 8.98 + 0.5 = 9.48 s -> 237
        self.assertEqual(report["removed_ranges"][0][0], "retake")
        self.assertIn(("retake", 3.0, 5.0), cuts)

    def test_gap_next_to_a_removal_is_not_shortened_twice(self):
        spec = [("a", 1.02, 1.42), ("b", 4.02, 4.42), ("c", 4.42, 4.82)]
        dec = {"linear": {"remove": [{"label": "x", "start": 1.0, "end": 1.5}]}}
        _, _, _, report = run(spec, decisions=dec)
        self.assertEqual(report["gaps_shortened"], [])


class Slivers(unittest.TestCase):
    RUSHES = (("A.MP4", 250), ("B.MP4", 250))                    # 10 s each

    def test_isolated_sliver_and_orphan_continuation_are_dropped(self):
        spec = [("Hello", 1.02, 1.42), ("friends.", 1.42, 6.02),
                ("So", 9.30, 9.62), ("let's", 9.62, 9.92),        # after a long gap, cut by the rush change
                ("do", 10.10, 10.30), ("it,", 10.30, 10.60),      # ...the sentence carries on in B
                ("and", 10.70, 11.02), ("then", 11.02, 11.42), ("more.", 11.42, 11.82)]
        ref, _, _, report = run(spec, rushes=self.RUSHES)
        # A: 18..163 kept; 220..250 (1.2 s, alone before the rush change) dropped; B's head "do it," dropped up
        # to "and" - 0.3 s = 10.40 s -> 260; tail 11.82 + 0.5 = 12.32 s -> 308
        self.assertEqual(ref, [[18, 163], [260, 308]])
        dropped = report["isolated_slivers_dropped"]
        self.assertEqual(len(dropped), 2)
        self.assertIn("orphan fragment", dropped[1])
        self.assertIn("do it,", dropped[1])

    def test_short_piece_joined_in_the_same_rush_is_kept(self):
        spec = [("Hi.", 1.02, 1.62), ("Yes", 1.62, 2.02), ("indeed.", 2.02, 2.42)]
        ref, _, _, report = run(spec, rushes=self.RUSHES)
        self.assertEqual(ref, [[18, 73], [250, 500]])              # 2.2 s: one piece; B (no speech) whole
        self.assertEqual(report["isolated_slivers_dropped"], [])

    def test_piece_shorter_than_min_isolated_is_dropped(self):
        ref, _, _, report = run([("Hi.", 1.02, 1.32)], rushes=self.RUSHES)   # 0.72 .. 1.82 s = 1.1 s
        self.assertEqual(ref, [[250, 500]])                         # only B (no speech) is left
        self.assertEqual(len(report["isolated_slivers_dropped"]), 1)


class Empty(unittest.TestCase):
    def test_no_words_keeps_everything(self):
        ref, cuts, demos, report = run([])
        self.assertEqual(ref, [[0, 500]])
        self.assertEqual((cuts, demos), ([], []))

    def test_rush_without_speech_is_kept_whole(self):
        ref, _, _, _ = run([("Hello.", 1.02, 2.02)], rushes=(("A.MP4", 250), ("B.MP4", 250)))
        self.assertEqual(ref, [[18, 63], [250, 500]])               # never cut a passage for lack of speech


class CommandLine(TempDirTest):
    def test_plan_pieces_markers(self):
        write_json(self.path("clips.json"), clips_data([("A.MP4", 500)]))
        write_json(self.path("t.json"), transcript([(t, s, e) for t, s, e in Gaps.SPEC]))
        write_json(self.path("decisions.json"), {"linear": {}})
        self.run_script("build_linear_edl.py", "decisions.json", "t.json", "clips.json", "plan.json",
                        "--profile", self.profile)
        plan = read_json(self.path("plan.json"))
        self.assertEqual(plan["kind"], "linear")
        self.assertEqual(plan["pieces"], [["A.MP4", 18, 113], ["A.MP4", 163, 208]])
        self.assertEqual(plan["total_frames"], 140)
        self.assertEqual([m[1:3] for m in plan["markers"]], [["Blue", "Blanc raccourci"]])
        self.assertEqual(plan["markers"][0][0], 95)                 # where the second piece starts in the timeline


if __name__ == "__main__":
    unittest.main()
