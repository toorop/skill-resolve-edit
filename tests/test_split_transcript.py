"""split_transcript.py: the reference transcript cut per rush, in each rush's own frames, for Resolve."""
import unittest

from helpers import TempDirTest, clips_data, read_json, transcript, write_json

from common import Clips
from split_transcript import language, speaker_name, split, to_frame


def W(text, start, end, speaker="speaker_0", typ="word"):
    return (text, start, end, speaker, typ)


class Helpers(unittest.TestCase):
    def test_language(self):
        self.assertEqual(language("fra"), "fr")
        self.assertEqual(language("en"), "en")
        self.assertIsNone(language("xyz"))
        self.assertIsNone(language(None))

    def test_speaker_name(self):
        self.assertEqual(speaker_name("speaker_0"), "Speaker 1")
        self.assertEqual(speaker_name("speaker_2"), "Speaker 3")
        self.assertIsNone(speaker_name(None))

    def test_halves_round_up(self):
        # Python's round() sends x.5 to the even number; frames must not depend on that
        self.assertEqual(to_frame(0.02, 25), 1)   # 0.5 frame
        self.assertEqual(to_frame(0.06, 25), 2)   # 1.5 frames
        self.assertEqual(to_frame(0.1, 25), 3)    # 2.5 frames
        self.assertEqual(to_frame(24.74, 25), 619)


class Split(unittest.TestCase):
    def setUp(self):
        # 25p reference: A (25p, 4 s), B (50p, 4 s = 200 rush frames), C (25p, 2 s, no speech)
        self.clips = Clips(clips_data([("A.MP4", 100, 25, "A"), ("B.MP4", 100, 50, "B"), ("C.MP4", 50, 25, "C")]))
        words = [W("Hello", 0.5, 0.9), W("to", 0.92, 0.92), W("all", 0.92, 1.2), W("!", 1.2, 1.2),
                 W("(laughs)", 1.3, 1.6, typ="audio_event"), W("Yes", 1.5, 1.7, "speaker_1"),
                 W("long", 3.5, 4.3),          # starts in A, ends in B: clipped to A's end
                 W("here", 4.02, 4.3), W("there", 6.0, 6.5), W("?", 6.5, 6.5), W("end", 7.9, 8.5)]
        self.res = split(transcript(words), self.clips)
        self.a, self.b, self.c = self.res["clips"]

    def test_language_and_rushes(self):
        self.assertEqual(self.res["language"], "en")
        self.assertEqual([c["short"] for c in self.res["clips"]], ["A", "B", "C"])

    def test_segments(self):
        texts = [[w["text"] for w in s["words"]] for s in self.a["segments"]]
        # sentence end, then speaker change, then a 1.8 s silence
        self.assertEqual(texts, [[" Hello", " to", " all!"], [" Yes"], [" long"]])
        self.assertEqual(self.a["segments"][1]["speaker"], "Speaker 2")
        self.assertEqual(self.a["segments"][0]["text"], " Hello to all!")

    def test_one_frame_minimum_and_no_overlap(self):
        words = self.a["segments"][0]["words"]
        self.assertEqual(words[1], {"text": " to", "start": 23, "end": 24})  # zero-length word: one frame
        self.assertEqual(words[2]["start"], 24)                              # starts where "to" ends
        self.assertEqual(self.a["shifted"], 1)

    def test_word_clipped_to_its_rush(self):
        self.assertEqual(self.a["segments"][2]["words"][0]["end"], 100)

    def test_50p_rush_in_a_25p_reference(self):
        self.assertEqual((self.b["fps"], self.b["frames"]), (50, 200))
        self.assertEqual(self.b["segments"][0]["words"][0], {"text": " here", "start": 1, "end": 15})
        self.assertEqual(self.b["segments"][1]["text"], " there?")
        self.assertEqual(self.b["segments"][1]["words"][0]["start"], 100)
        self.assertEqual(self.b["segments"][2]["words"][0], {"text": " end", "start": 195, "end": 200})

    def test_rush_without_speech(self):
        self.assertEqual((self.c["segments"], self.c["n_words"]), ([], 0))

    def test_no_speakers(self):
        res = split(transcript([W("Hi", 0.2, 0.5)]), self.clips, speakers=False)
        self.assertNotIn("speaker", res["clips"][0]["segments"][0])

    def test_frames_are_ordered_inside_every_rush(self):
        for c in self.res["clips"]:
            prev = 0
            for s in c["segments"]:
                self.assertLessEqual(prev, s["start"])
                for w in s["words"]:
                    self.assertLessEqual(prev, w["start"])
                    self.assertLess(w["start"], w["end"])
                    self.assertLessEqual(w["end"], c["frames"])
                    prev = w["end"]


class CommandLine(TempDirTest):
    def test_writes_the_file_with_the_rushes_folder(self):
        write_json(self.path("clips.json"), clips_data([("A.MP4", 100)]))
        write_json(self.path("transcript.json"), transcript([W("Hi", 0.2, 0.5)], "fra"))
        p = self.run_script("split_transcript.py", "transcript.json", "clips.json", "out.json")
        out = read_json(self.path("out.json"))
        self.assertEqual(out["rushes_dir"], "/rushes")
        self.assertEqual(out["language"], "fr")
        self.assertIn("1 rushes, 1 words", p.stdout)


if __name__ == "__main__":
    unittest.main()
