"""history.py (proposals vs validations) and final_changes.py (built montage vs the user's FINAL)."""
import os
import unittest

from helpers import TempDirTest, read_json, write_json

from final_changes import compare as final_compare
from final_changes import longest_increasing, merge, subtract
from history import compare_removals, compare_sequences


class Intervals(unittest.TestCase):
    def test_merge_and_subtract(self):
        self.assertEqual(merge([[5, 8], [0, 3], [2, 4], [8, 9]]), [[0, 4], [5, 9]])
        self.assertEqual(subtract([[0, 10]], [[2, 3], [5, 12]]), [[0, 2], [3, 5]])
        self.assertEqual(subtract([[0, 10]], []), [[0, 10]])
        self.assertEqual(subtract([[0, 10]], [[0, 10]]), [])

    def test_longest_increasing(self):
        self.assertEqual(longest_increasing([0, 1, 2]), {0, 1, 2})
        self.assertEqual(len(longest_increasing([0, 3, 1, 2])), 3)        # only "3" moved
        self.assertNotIn(1, longest_increasing([0, 3, 1, 2]))


class FinalChanges(unittest.TestCase):
    PLAN = {"fps": 25, "pieces": [["A.MP4", 0, 100], ["B.MP4", 50, 150], ["A.MP4", 200, 260], ["C.MP4", 0, 40]],
            "tail_pieces": [["A.MP4", 300, 350]],
            "sequences": [{"title": "One", "first": ["A.MP4", 0, 100]}, {"title": "Two", "first": ["B.MP4", 50, 150]},
                          {"title": "Three", "first": ["A.MP4", 200, 260]}]}

    def final(self, items):
        return {"fps": 25.0, "frames": 1000, "items": items}

    def test_untouched(self):
        res = final_compare(self.PLAN, self.final([
            [1, "A.MP4", "video", 0, 100, 0], [1, "B.MP4", "video", 100, 200, 50], [1, "A.MP4", "video", 200, 260, 200],
            [1, "C.MP4", "video", 260, 300, 0], [1, "Text+", "video", 300, 425, 0],
            [1, "A.MP4", "video", 425, 475, 300]]))
        self.assertEqual((res["main"]["removed"], res["main"]["added"], res["moved"]), ([], [], []))
        self.assertEqual(res["bloopers"]["removed"], [])

    def test_trims_removals_additions_moves_overlays(self):
        res = final_compare(self.PLAN, self.final([
            [1, "B.MP4", "video", 0, 100, 50],          # "Two" moved first
            [1, "A.MP4", "video", 100, 190, 10],        # head of A trimmed by 10 frames
            [1, "A.MP4", "video", 190, 270, 200],       # "Three" lengthened by 20 frames (260..280)
            [2, "D.MP4", "video", 20, 60, 0],           # another clip on V2
            [2, "B.MP4", "video", 120, 130, 160],       # a B shot put on V2 (not in the montage: added)
            [1, "Text+", "video", 300, 425, 0]]))       # C removed; bloopers gone
        main = res["main"]
        self.assertEqual([(r["clip"], r["src"], r["whole_piece"]) for r in main["removed"]],
                         [("A.MP4", [0, 10], False), ("C.MP4", [0, 40], True)])
        self.assertEqual(main["removed"][1]["montage_at"], 260)
        self.assertEqual([(a["clip"], a["src"], a["final_at"]) for a in main["added"]],
                         [("A.MP4", [260, 280], 250), ("B.MP4", [160, 170], 120)])
        self.assertEqual([m["title"] for m in res["moved"]], ["Two"])
        self.assertEqual([(v["clip"], v["track"]) for v in res["on_v2"]], [("B.MP4", 2)])
        self.assertEqual([o["name"] for o in res["other"]], ["D.MP4"])
        self.assertEqual(res["bloopers"]["removed"][0]["src"], [300, 350])

    def test_tiny_differences_are_ignored(self):
        res = final_compare(self.PLAN, self.final([
            [1, "A.MP4", "video", 0, 99, 0], [1, "B.MP4", "video", 99, 199, 50], [1, "A.MP4", "video", 199, 259, 200],
            [1, "C.MP4", "video", 259, 299, 0]]), min_frames=2)
        self.assertEqual(res["main"]["removed"], [])


class Comparisons(unittest.TestCase):
    def test_removals(self):
        proposed = [{"label": "false start", "start": 10.0, "end": 14.0, "reason": "retake"},
                    {"label": "cameraman", "start": 60.0, "end": 70.0},
                    {"label": "politics", "start": 100.0, "end": 120.0}]
        validated = [{"label": "false start", "start": "00:00:10:05", "end": 14.0},
                     {"label": "cameraman", "start": 58.0, "end": 70.0},
                     {"label": "noise", "start": 200.0, "end": 201.0}]
        r = compare_removals(proposed, validated, 25)
        self.assertEqual([x["label"] for x in r["accepted"]], ["false start"])
        self.assertEqual([(x["label"], x["shift_start"]) for x in r["adjusted"]], [("cameraman", -2.0)])
        self.assertEqual([x["label"] for x in r["refused"]], ["politics"])
        self.assertEqual([x["label"] for x in r["added_by_user"]], ["noise"])

    def test_sequences(self):
        p = [{"title": "Intro", "ranges": [[0, 10]]}, {"title": "Clock", "ranges": [[10, 50]]},
             {"title": "Vase", "ranges": [[50, 90]]}, {"title": "Outro", "ranges": [[90, 99]]}]
        v = [{"title": "Intro", "ranges": [[0, 10]]}, {"title": "Vase", "ranges": [[50, 95]]},
             {"title": "Clock", "ranges": [[10, 50]]}, {"title": "Bonus", "ranges": [[100, 110]]}]
        r = compare_sequences(p, v)
        self.assertEqual(r["kept_same_place"], ["Intro"])
        self.assertEqual([m["title"] for m in r["moved"]], ["Clock", "Vase"])
        self.assertEqual(r["dropped"], ["Outro"])
        self.assertEqual(r["added_by_user"], ["Bonus"])
        self.assertEqual(r["ranges_changed"], ["Vase"])


class CommandLine(TempDirTest):
    def test_save_versions_and_compare(self):
        write_json(self.path("resolve-edit.json"), {"profile": "profile"})
        write_json(self.path("prop.json"), {"linear": {"remove": [{"label": "x", "start": 1.0, "end": 2.0}]}})
        with open(self.path("prop.md"), "w", encoding="utf-8") as f:
            f.write("# Derushage\n")
        write_json(self.path("decisions.json"), {"fps": 25, "linear": {"remove": [{"label": "x", "start": 1.0, "end": 2.0}]}})
        self.run_script("history.py", "save", "derushage_proposal", "prop.md", "--model", "test-model")
        self.run_script("history.py", "save", "derushage_proposal", "prop.json")
        self.run_script("history.py", "save", "decisions_linear", "decisions.json")
        self.run_script("history.py", "save", "decisions_linear", "decisions.json")
        files = sorted(os.listdir(self.path("history")))
        self.assertEqual(files, ["04_derushage_proposal.json", "04_derushage_proposal.md", "decisions_linear_v1.json",
                                 "decisions_linear_v2.json", "meta.json"])
        meta = read_json(self.path("history", "meta.json"))
        self.assertEqual(meta["profile"], "profile")
        self.assertEqual([s["kind"] for s in meta["saves"]].count("decisions_linear"), 2)
        self.assertEqual(meta["saves"][0]["model"], "test-model")
        self.assertEqual(len(meta["saves"][0]["skill"]), 12)
        out = self.run_script("history.py", "compare").stdout
        self.assertIn("accepted 1, adjusted 0, refused 0, added by the user 0", out)
        self.assertTrue(os.path.exists(self.path("history", "comparison.json")))

    def test_second_proposal_is_kept(self):
        with open(self.path("p.md"), "w") as f:
            f.write("x")
        self.run_script("history.py", "save", "montage_proposal", "p.md")
        self.run_script("history.py", "save", "montage_proposal", "p.md")
        self.assertTrue(os.path.exists(self.path("history", "06_montage_proposal_2.md")))

    def test_broken_json_and_nothing_to_compare(self):
        with open(self.path("bad.json"), "w") as f:
            f.write("{oops")
        self.assertNotEqual(self.run_script("history.py", "save", "montage_proposal", "bad.json", check=False).returncode, 0)
        p = self.run_script("history.py", "compare", check=False)
        self.assertIn("nothing to compare", p.stdout + p.stderr)

    def test_final_changes_command(self):
        write_json(self.path("plan.json"), FinalChanges.PLAN)
        write_json(self.path("final.json"), {"fps": 25.0, "frames": 300, "items": [[1, "A.MP4", "video", 0, 100, 0]]})
        out = self.run_script("final_changes.py", "plan.json", "final.json", "history/09_final_changes").stdout
        self.assertIn("piece removed: C 1.6s at montage 00:00:10:10", out)
        self.assertIn("## Sequences gone: Two, Three", out)
        self.assertTrue(os.path.exists(self.path("history", "09_final_changes.json")))


if __name__ == "__main__":
    unittest.main()
