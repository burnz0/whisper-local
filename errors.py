from __future__ import annotations


def friendly_transcription_error(exc: Exception) -> tuple[str, int]:
    message = str(exc).strip()
    lowered = message.lower()

    if isinstance(exc, ValueError):
        if "format" in lowered or "supported" in lowered:
            return "This audio format is not supported. Choose an opus, oga, ogg, mp3, wav, m4a, flac, webm, or similar audio file.", 400
        if "model" in lowered:
            return message or "Choose a supported Whisper model.", 400
        return message or "The selected audio file could not be used.", 400

    if isinstance(exc, FileNotFoundError) or "ffmpeg" in lowered:
        return "FFmpeg is required to read this audio file. Install ffmpeg and try again.", 500

    if "cuda" in lowered or "gpu" in lowered:
        return "GPU processing failed. Try a smaller model or switch to CPU processing and run the transcription again.", 500

    if any(token in lowered for token in ("decode", "invalid data", "corrupt", "moov atom", "could not open", "no such file")):
        return "This audio file could not be decoded. Try converting it to wav or mp3, then upload it again.", 400

    if "model" in lowered or "whisper" in lowered:
        return f"Whisper could not process this file: {message or exc.__class__.__name__}", 500

    return f"Transcription failed: {message or exc.__class__.__name__}", 500
