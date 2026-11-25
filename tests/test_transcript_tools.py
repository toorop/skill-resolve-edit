"""merge_transcripts.py, flag_passages.py, readable_transcript.py."""
import unittest

from helpers import TempDirTest, clips_data, read_json, sentence, transcript, write_json


class Merge(TempDirTest):
    def test_parts_are_shifted_by_their_offset(self):
        write_json(self.path("p1.json"), transcript([("One", 0.5, 0.8), ("two", 1.0, 1.3)], "fra"))
        write_json(self.path("p2.json"), transcript([("Three", 0.2, 0.6)], "fra"))
        self.run_script("merge_transcripts.py", "out.json", "p1.json:0", "p2.json:1006.08")
        out = read_json(self.path("out.json"))
        words = [w for w in out["words"] if w["type"] == "word"]
        self.assertEqual([(w["text"], w["start"], w["end"]) for w in words],
                         [("One", 0.5, 0.8), ("two", 1.0, 1.3), ("Three", 1006.28, 1006.68)])
        self.assertEqual(out["language_code"], "fra")
        self.assertEqual(out["text"], "One twoThree")
        self.assertEqual([p["offset"] for p in out["parts"]], [0.0, 1006.08])

    def test_manifest(self):
        write_json(self.path("parts", "ref16k_part1.json"), transcript([("A", 0.1, 0.2)]))
        write_json(self.path("parts", "ref16k_part2.json"), transcript([("B", 0.1, 0.2)]))
        write_json(self.path("parts", "manifest.json"), [
            {"file": self.path("parts", "ref16k_part1.wav"), "offset": 0, "duration": 10},
            {"file": self.path("parts", "ref16k_part2.wav"), "offset": 10, "duration": 5}])
        self.run_script("merge_transcripts.py", "out.json", "--manifest", self.path("parts", "manifest.json"))
        starts = [w["start"] for w in read_json(self.path("out.json"))["words"] if w["type"] == "word"]
        self.assertEqual(starts, [0.1, 10.1])

    def test_wrong_offsets_are_refused(self):
        write_json(self.path("p1.json"), transcript([("A", 5.0, 5.2)]))
        write_json(self.path("p2.json"), transcript([("B", 0.1, 0.2)]))
        p = self.run_script("merge_transcripts.py", "out.json", "p1.json:0", "p2.json:2", check=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("chronological", p.stdout + p.stderr)


class Flags(TempDirTest):
    def setUp(self):
        super().setUp()
        write_json(self.path("clips.json"), clips_data([("A0001.MP4", 500, 25, "A0001"), ("A0002.MP4", 500, 25, "A0002")]))
        words = (sentence("Damn this shortcut is damned good.", 1.0)
                 + sentence("Cut let me start again with the cutlery.", 25.0))
        write_json(self.path("t.json"), transcript(words))

    def test_patterns_from_the_profile_match_at_word_start(self):
        out = self.run_script("flag_passages.py", "t.json", "clips.json", "--profile", self.profile).stdout
        # "damn\b": Damn yes, "damned" no; "cut\b": Cut yes, "shortcut" and "cutlery" no
        self.assertIn("## swearing (1)", out)
        self.assertIn("## retake (2)", out)
        self.assertIn("A0001", out.split("## retake")[0])
        retake = out.split("## retake")[1]
        self.assertIn("[cut]", retake)
        self.assertIn("[let me start again]", retake)
        self.assertIn("00:00:25:00 A0002", retake)

    def test_no_flags_in_the_profile(self):
        write_json(self.path("empty", "settings.json"), {"language": "en"})
        p = self.run_script("flag_passages.py", "t.json", "clips.json", "--profile", self.path("empty"), check=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("No \"flags\"", p.stdout + p.stderr)


class Readable(TempDirTest):
    def test_sentences_rushes_silences_speakers(self):
        write_json(self.path("clips.json"), clips_data([("A0001.MP4", 500, 25, "A0001"), ("A0002.MP4", 500, 25, "A0002")]))
        words = (sentence("Hello and welcome.", 1.0) + sentence("Today we look", 2.2)
                 + sentence("at a clock.", 5.0)                              # "look" ends at 3.3: 1.7 s silence
                 + sentence("Nice one", 6.4, speaker="speaker_1")            # another voice
                 + sentence("Second rush here.", 21.0))
        write_json(self.path("t.json"), transcript(words))
        self.run_script("readable_transcript.py", "t.json", "clips.json", "out.txt", "--profile", self.profile)
        with open(self.path("out.txt"), encoding="utf-8") as f:
            lines = [l.rstrip() for l in f.read().strip().splitlines() if l.strip()]
        self.assertEqual(lines, [
            "=== A0001  (00:00:01:00)",
            "00:00:01:00  Hello and welcome.",
            "00:00:02:05  Today we look",
            "            ... silence 1.7s",
            "00:00:05:00  at a clock.",
            "00:00:06:10  [speaker_1] Nice one",
            "=== A0002  (00:00:21:00)",
            "00:00:21:00  Second rush here.",
        ])


if __name__ == "__main__":
    unittest.main()
