"""Speech-to-text for video parts using the LLM's audio input (no Whisper needed).

    from ads.preprocess.transcribe import transcribe_video
    text = transcribe_video("clip.mp4", "data/cases/14/audio_0.mp3")   # '' when there is no speech

Audio is extracted with the ffmpeg binary bundled in `imageio-ffmpeg` (mono, 16 kHz, 32 kbit/s mp3,
so even long recordings stay far below the inline-upload limit) and sent to Gemini with a
transcription-only instruction. Results are cached like any other LLM call.
"""
import os
import subprocess
from typing import Optional

from ..llm.client import make_client

PROMPT = ("You are a transcription engine. Transcribe the speech in this audio verbatim in its original language "
          "(usually Polish). Output only the transcript as plain text: no timestamps, no speaker labels, no commentary, "
          "no translation. Repeated sentences stay repeated. If there is no intelligible speech, output exactly: NO_SPEECH")


def extract_audio(video_path: str, out_path: str) -> str:
    import imageio_ffmpeg
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", video_path, "-vn",
                        "-ac", "1", "-ar", "16000", "-b:a", "32k", out_path], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
        raise RuntimeError(f"no audio track extracted ({r.stderr.strip()[:200]})")
    return out_path


def transcribe_video(video_path: str, audio_path: str, model: Optional[str] = None) -> str:
    extract_audio(video_path, audio_path)
    client = make_client("extraction_model", json_mode=False, **({"extraction_model": model} if model else {}))
    text = client.generate_text(PROMPT, [("audio", audio_path)]).strip()
    return "" if text == "NO_SPEECH" else text
