# Transcription — ElevenLabs Scribe v2 via fal.ai

## Why this engine
- Word-level timestamps, spacing tokens, audio events ([rire], [bruit]), diarization, excellent French.
- Whisper-family models (incl. large-turbo, WhisperX) CLEAN disfluencies and get worse on long files — rejected.
- ElevenLabs direct requires a subscription; fal.ai is pay-per-use: ~$0.008 / audio minute (+30% with keyterms).
  A 35 min video ≈ $0.30.

## API (implemented in transcribe_fal.py, stdlib only)
- Upload: `POST https://rest.alpha.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3` ("gcs" is rejected:
  "Invalid storage type") (Authorization: `Key <key>`,
  JSON `{file_name, content_type}`) → `{upload_url, file_url}`; then `PUT upload_url` with the bytes.
  (Files > 100 MB would need multipart; our 16 kHz mono parts are ~35 MB.)
- Submit: `POST https://queue.fal.run/fal-ai/elevenlabs/speech-to-text/scribe-v2` with
  `{audio_url, language_code?: "fr", tag_audio_events: true, diarize: true, keyterms?: [...]}` → `status_url`,
  `response_url`; poll until `COMPLETED`; GET the result.
- Output: `{text, language_code, language_probability, words: [{text, start, end, type: word|spacing|audio_event,
  speaker_id}]}`.
- The web form (fal.ai playground) works too but pastes the huge JSON into a browser field — avoid.
- Verified 2026-09-24 on a 2 min part: ~10 s, same words and timings as the web form (median 0 ms, max 40 ms).

## Limits and format choices
- **Max 1200 s per file** → `prepare_audio.py` splits at rush boundaries (sample-exact) below 1150 s and the merge
  adds each part's offset.
- Accepted formats: mp3, ogg, wav, m4a, aac — **no FLAC**. Use **WAV 16 kHz mono**: speech models work at 16 kHz,
  zero timing offset (verified by cross-correlation), ~67 MB for 35 min. MP3/AAC add encoder priming → shifted
  timestamps: never use them.
- A lavalier recorded on both camera channels (same voice on L and R) loses nothing in mono; check the L-R
  difference if a second microphone may be on the other channel.

## What to expect
- Fluent presenters produce few fillers: the "noise" to cut is retakes, false starts, off-topic and long gaps.
- Audible gaps between words are often breaths: leave them.
- Long "words" or silences can be demonstrations ("Hop" lasting 2.9 s while opening a device).
- Muttered words can be missing. Energy/zero-crossing detection cannot tell breaths from muttering (tested) —
  don't build alerts on it.
- Tokens are not always contiguous: compute gaps from word end → next word start, not from spacing tokens.
- A word can be stretched over non-speech (e.g. "Hello" spanning 23 s over a car arrival).
