"""build_montage.py, chapters.py, thumbnail_candidates.py."""
import unittest

from helpers import TempDirTest, clips_data, read_json, transcript, write_json


def steady_speech(start, end, step=0.4):
    """One word every `step` s from `start` to `end`: no gap long enough to be shortened."""
    out, k = [], 0
    while round(start + k * step + step - 0.04, 2) <= end:
        s = round(start + k * step, 2)
        out.append(("w%d" % len(out), s, round(s + step - 0.04, 2)))
        k += 1
    return out


class Montage(TempDirTest):
    def setUp(self):
        super().setUp()
        write_json(self.path("clips.json"), clips_data([("A.MP4", 500), ("B.MP4", 500)]))  # 20 s each
        # A speaks 1.02 .. 18.98 s, B 21.02 .. 38.98 s -> clean material [18, 487] and [518, 987]
        write_json(self.path("t.json"), transcript(steady_speech(1.02, 18.98) + steady_speech(21.02, 38.98)))

    def build(self, montage):
        write_json(self.path("decisions.json"), {"linear": {}, "montage": montage})
        self.run_script("build_montage.py", "decisions.json", "t.json", "clips.json", "plan.json",
                        "--profile", self.profile)
        return read_json(self.path("plan.json"))

    def test_sequences_in_the_chosen_order_with_material_from_elsewhere(self):
        plan = self.build({"sequences": [{"title": "Intro", "ranges": [[20.0, 30.0]]},
                                         {"title": "Clock", "ranges": [[0, 10.0], ["00:00:30:00", 35.0]]}]})
        self.assertEqual(plan["kind"], "montage")
        self.assertEqual(plan["pieces"], [["B.MP4", 18, 250], ["A.MP4", 18, 250], ["B.MP4", 250, 375]])
        self.assertEqual(plan["main_frames"], 589)
        self.assertEqual(plan["sequences"], [{"title": "Intro", "frame": 0, "first": ["B.MP4", 18, 250]},
                                             {"title": "Clock", "frame": 232, "first": ["A.MP4", 18, 250]}])
        self.assertEqual([m[:3] for m in plan["markers"]],
                         [[0, "Purple", "Intro"], [232, "Purple", "Clock"], [464, "Cyan", "Raccord deplace"]])
        self.assertIsNone(plan["title"])

    def test_bloopers_after_a_title_card(self):
        plan = self.build({"sequences": [{"title": "Intro", "ranges": [[20.0, 30.0]]}],
                           "bloopers": [{"label": "Ça rate", "start": 12.0, "end": 14.0},
                                        {"label": "Again", "end": 25.0}]})   # from just before the first word
        self.assertEqual(plan["title"], {"text": "Bloopers"})              # from the profile
        self.assertEqual(plan["tail_pieces"], [["A.MP4", 300, 350], ["B.MP4", 18, 125]])
        self.assertEqual(plan["tail_frames"], 157)
        self.assertEqual(plan["tail_markers"], [[0, "Pink", "Ca rate", "Betisier"], [50, "Pink", "Again", "Betisier"]])

    def test_empty_sequence_is_reported_and_skipped(self):
        write_json(self.path("decisions.json"), {"montage": {"sequences": [
            {"title": "Silence", "ranges": [[19.5, 20.5]]}, {"title": "Intro", "ranges": [[20.0, 30.0]]}]}})
        p = self.run_script("build_montage.py", "decisions.json", "t.json", "clips.json", "plan.json",
                            "--profile", self.profile)
        self.assertIn("sequence 'Silence' is empty", p.stdout)
        self.assertEqual([s["title"] for s in read_json(self.path("plan.json"))["sequences"]], ["Intro"])


class Chapters(TempDirTest):
    def test_chapters_follow_the_final(self):
        seq = lambda t, first: {"title": t, "frame": 0, "first": first}
        write_json(self.path("plan.json"), {"fps": 25, "title": {"text": "Bloopers"}, "sequences": [
            seq("Intro", ["A.MP4", 0, 100]),
            seq("Second", ["B.MP4", 0, 50]),
            seq("Third", ["A.MP4", 200, 300]),
            seq("Too close", ["C.MP4", 0, 50]),        # 2 s after Third: under 10 s, merged into it
            seq("Gone", ["D.MP4", 0, 50]),             # removed by hand
            seq("Trimmed", ["B.MP4", 100, 200]),       # its head trimmed by hand: found by a later piece
            seq("Only blooper", ["E.MP4", 0, 50])]})   # only after the title card: not a chapter
        items = [[1, "A.MP4", "video", 0, 100, 0],
                 [1, "B.MP4", "video", 250, 300, 0],
                 [2, "A.MP4", "video", 1000, 1100, 150],
                 [1, "C.MP4", "video", 1100, 1200, 0],
                 [1, "B.MP4", "video", 1500, 1600, 120],
                 [1, "Text+", "video", 2000, 2125, 0],
                 [1, "E.MP4", "video", 2125, 2200, 0]]
        write_json(self.path("final.json"), {"fps": 25.0, "frames": 2200, "items": items})
        out = self.run_script("chapters.py", "plan.json", "final.json").stdout.splitlines()
        self.assertEqual([l for l in out if " - " in l and not l.startswith("#")],
                         ["00:00 - Intro", "00:10 - Second", "00:42 - Third", "01:00 - Trimmed", "01:20 - Bloopers"])
        self.assertIn("# not found in FINAL (removed?): ['Gone', 'Only blooper']", out)

    def test_first_chapter_at_zero_and_warning_under_three(self):
        write_json(self.path("plan.json"), {"fps": 25, "title": None, "sequences": [
            {"title": "Late start", "frame": 0, "first": ["A.MP4", 0, 50]}]})
        write_json(self.path("final.json"), {"fps": 25.0, "frames": 400,
                                             "items": [[1, "X.MP4", "video", 0, 125, 0], [1, "A.MP4", "video", 125, 400, 0]]})
        out = self.run_script("chapters.py", "plan.json", "final.json").stdout
        self.assertIn("00:00 - Late start", out)
        self.assertIn("at least 3 chapters", out)


class Thumbnails(TempDirTest):
    def setUp(self):
        super().setUp()
        write_json(self.path("clips.json"), clips_data([("A.MP4", 1500, 25, "A")]))       # 60 s
        words = [("look", 2.02, 2.3), ("at", 2.3, 2.5), ("this", 2.5, 2.8),
                 ("a", 4.9, 5.02), ("treasure", 5.02, 5.6),       # weight 3, 3 s after "look at" (weight 1)
                 ("so", 30.0, 30.02), ("gorgeous", 30.02, 30.6),
                 ("look", 50.02, 50.3), ("at", 50.3, 50.5), ("that", 50.5, 50.8)]   # only in the bloopers
        write_json(self.path("t.json"), transcript(words))
        # FINAL: A 0..48 s, then the title card and a blooper taken from A's end
        write_json(self.path("final.json"), {"fps": 25.0, "frames": 1500, "items": [
            [1, "A.MP4", "video", 0, 1200, 0], [1, "Text+", "video", 1200, 1325, 0],
            [1, "A.MP4", "video", 1325, 1500, 1250]]})

    def test_candidates_strongest_per_window_only_in_the_final(self):
        out = self.run_script("thumbnail_candidates.py", "t.json", "clips.json", "final.json", "vign",
                              "--profile", self.profile).stdout
        cands = read_json(self.path("vign", "candidates.json"))
        self.assertEqual([(c["id"], c["cue"], c["final_tc"], c["rush_short"]) for c in cands],
                         [(1, "treasure", "00:00:06:13", "A"), (2, "gorgeous", "00:00:31:13", "A")])
        self.assertEqual(read_json(self.path("vign", "sheet_frames.json")),
                         [{"frame": 163, "label": "1  00:06"}, {"frame": 788, "label": "2  00:31"}])
        self.assertIn("2 candidates", out)

    def test_export_picks(self):
        self.run_script("thumbnail_candidates.py", "t.json", "clips.json", "final.json", "vign", "--profile", self.profile)
        self.run_script("thumbnail_candidates.py", "t.json", "clips.json", "final.json", "vign", "--export", "2",
                        "--profile", self.profile)
        self.assertEqual(read_json(self.path("vign", "export_frames.json")),
                         [{"frame": 788, "name": "vignette_02_00003113.png"}])
        p = self.run_script("thumbnail_candidates.py", "t.json", "clips.json", "final.json", "vign", "--export", "3",
                            "--profile", self.profile, check=False)
        self.assertIn("no candidate [3]", p.stdout + p.stderr)

    def test_max_and_no_cues(self):
        self.run_script("thumbnail_candidates.py", "t.json", "clips.json", "final.json", "vign", "--max", "1",
                        "--profile", self.profile)
        self.assertEqual([c["cue"] for c in read_json(self.path("vign", "candidates.json"))], ["treasure"])
        write_json(self.path("empty", "settings.json"), {"language": "en"})
        p = self.run_script("thumbnail_candidates.py", "t.json", "clips.json", "final.json", "vign",
                            "--profile", self.path("empty"), check=False)
        self.assertIn("No thumbnail \"cues\"", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
