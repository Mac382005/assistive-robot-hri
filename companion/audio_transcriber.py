from __future__ import annotations

import base64
import os
import re
import tempfile
import time

import config

try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None


class AudioTranscriber:
    """Gemini-backed speech-to-text adapter for short tablet voice turns."""

    def __init__(self) -> None:
        self.enabled = bool(config.AI_ENABLED)
        self.api_key = str(config.GEMINI_API_KEY or "").strip()
        self.model = str(config.GEMINI_TRANSCRIBE_MODEL or "gemini-3.5-transcribe").strip()
        self.fallback_model = str(
            getattr(config, "GEMINI_MODEL", "gemini-3.5-flash-lite")
            or "gemini-3.5-flash-lite"
        ).strip()
        self.client = None
        self.last_error: str | None = None
        self.last_info: dict = {}

        if self.enabled and self.api_key and genai is not None:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"

    @property
    def api_available(self) -> bool:
        return bool(self.enabled and self.api_key and self.client is not None)

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "configured": bool(self.api_key),
            "api_available": self.api_available,
            "provider": "gemini",
            "model": self.model if self.api_available else None,
            "fallback_model": self.fallback_model if self.api_available else None,
            "last_error": self.last_error,
            "last_info": self.last_info,
        }

    @staticmethod
    def normalise_mime_type(mime_type: str | None) -> str:
        value = str(mime_type or "audio/webm").strip().lower()
        value = value.split(";", 1)[0].strip()
        aliases = {
            "audio/x-m4a": "audio/m4a",
            "audio/mp4": "audio/m4a",
            "audio/x-wav": "audio/wav",
            "audio/mpeg3": "audio/mpeg",
            "audio/x-mpeg": "audio/mpeg",
        }
        return aliases.get(value, value)

    @staticmethod
    def suffix_for_mime(mime_type: str) -> str:
        return {
            "audio/webm": ".webm",
            "audio/m4a": ".m4a",
            "audio/mpeg": ".mp3",
            "audio/mp3": ".mp3",
            "audio/wav": ".wav",
            "audio/aac": ".aac",
            "audio/ogg": ".ogg",
            "audio/flac": ".flac",
            "audio/aiff": ".aiff",
            "audio/opus": ".opus",
        }.get(mime_type, ".audio")

    @staticmethod
    def _state_name(file_obj) -> str:
        state = getattr(file_obj, "state", None)
        if state is None:
            return ""
        name = getattr(state, "name", None)
        if name:
            return str(name).upper()
        value = str(state).upper()
        for known in ("PROCESSING", "ACTIVE", "FAILED"):
            if known in value:
                return known
        return value

    def _wait_until_ready(self, remote_file, timeout_seconds: float = 12.0):
        deadline = time.monotonic() + timeout_seconds
        current = remote_file
        while True:
            state = self._state_name(current)
            if state in {"", "ACTIVE"}:
                return current
            if state == "FAILED":
                raise RuntimeError("Gemini could not process the uploaded audio file.")
            if state != "PROCESSING":
                return current
            if time.monotonic() >= deadline:
                raise RuntimeError("Gemini audio processing timed out.")
            time.sleep(0.20)
            current = self.client.files.get(name=current.name)

    @staticmethod
    def _clean_text(value: object) -> str:
        text = str(value or "").strip()
        text = re.sub(r"^```(?:text)?\s*|\s*```$", "", text, flags=re.I)
        return re.sub(r"\s+", " ", text).strip()

    def _transcribe_inline_interactions(self, audio_bytes: bytes, mime_type: str) -> str:
        """Fast path: one request, no temporary Gemini Files upload."""
        interactions = getattr(self.client, "interactions", None)
        if interactions is None or not hasattr(interactions, "create"):
            return ""

        encoded = base64.b64encode(audio_bytes).decode("ascii")
        interaction = interactions.create(
            model=self.model,
            input=[
                {
                    "type": "audio",
                    "data": encoded,
                    "mime_type": mime_type,
                }
            ],
            generation_config={
                "transcription_config": {
                    "mode": "smart",
                }
            },
        )
        return self._clean_text(getattr(interaction, "output_text", ""))

    def _transcribe_inline_multimodal(self, audio_bytes: bytes, mime_type: str) -> str:
        if types is None:
            return ""
        response = self.client.models.generate_content(
            model=self.fallback_model,
            contents=[
                (
                    "Transcribe the spoken words in this short recording accurately. "
                    "Return only the transcript, with no commentary. "
                    "If there is genuinely no intelligible speech, return NO_SPEECH."
                ),
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            ],
        )
        text = self._clean_text(getattr(response, "text", ""))
        return "" if text.upper() == "NO_SPEECH" else text

    def _transcribe_via_file_api(self, audio_bytes: bytes, mime_type: str) -> str:
        """Compatibility fallback for SDK/model combinations that reject inline audio."""
        local_path: str | None = None
        remote_file = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=self.suffix_for_mime(mime_type), delete=False
            ) as temp:
                temp.write(audio_bytes)
                local_path = temp.name

            try:
                remote_file = self.client.files.upload(
                    file=local_path,
                    config={"mime_type": mime_type},
                )
            except TypeError:
                remote_file = self.client.files.upload(file=local_path)

            remote_file = self._wait_until_ready(remote_file)
            interactions = getattr(self.client, "interactions", None)
            if interactions is not None and hasattr(interactions, "create"):
                interaction = interactions.create(
                    model=self.model,
                    input=[
                        {
                            "type": "audio",
                            "uri": remote_file.uri,
                            "mime_type": getattr(remote_file, "mime_type", None) or mime_type,
                        }
                    ],
                    generation_config={"transcription_config": {"mode": "smart"}},
                )
                text = self._clean_text(getattr(interaction, "output_text", ""))
                if text:
                    return text

            response = self.client.models.generate_content(
                model=self.model,
                contents=[remote_file],
            )
            return self._clean_text(getattr(response, "text", ""))
        finally:
            if remote_file is not None:
                try:
                    self.client.files.delete(name=remote_file.name)
                except Exception:
                    pass
            if local_path:
                try:
                    os.remove(local_path)
                except OSError:
                    pass

    def transcribe(self, audio_bytes: bytes, mime_type: str | None) -> str:
        if not self.api_available:
            raise RuntimeError("Gemini voice transcription is not configured or is unavailable.")
        if not audio_bytes:
            raise ValueError("The audio recording was empty.")
        if len(audio_bytes) < 1024:
            raise ValueError("The audio recording was too small to contain a usable voice turn.")

        clean_mime = self.normalise_mime_type(mime_type)
        allowed = {
            "audio/webm", "audio/m4a", "audio/mpeg", "audio/mp3",
            "audio/wav", "audio/aac", "audio/ogg", "audio/flac",
            "audio/aiff", "audio/opus",
        }
        if clean_mime not in allowed:
            raise ValueError(f"Unsupported audio format: {clean_mime}")

        started = time.perf_counter()
        self.last_info = {
            "bytes": len(audio_bytes),
            "mime_type": clean_mime,
            "stage": "received",
        }
        errors: list[str] = []

        try:
            text = ""

            # V4.3.2 fast path. Short conversational recordings are small and
            # transient, so sending the bytes inline avoids upload/process/delete
            # round trips through the Gemini Files API.
            try:
                text = self._transcribe_inline_interactions(audio_bytes, clean_mime)
                if text:
                    self.last_info["method"] = "inline_interactions"
            except Exception as exc:
                errors.append(f"inline interactions: {type(exc).__name__}: {exc}")

            if not text:
                try:
                    text = self._transcribe_inline_multimodal(audio_bytes, clean_mime)
                    if text:
                        self.last_info["method"] = "inline_multimodal"
                except Exception as exc:
                    errors.append(f"inline fallback: {type(exc).__name__}: {exc}")

            if not text:
                try:
                    text = self._transcribe_via_file_api(audio_bytes, clean_mime)
                    if text:
                        self.last_info["method"] = "file_api_fallback"
                except Exception as exc:
                    errors.append(f"file fallback: {type(exc).__name__}: {exc}")

            if not text:
                detail = "; ".join(errors[-2:])
                message = (
                    f"Gemini could not detect speech in the {len(audio_bytes)}-byte "
                    f"{clean_mime} recording."
                )
                if detail:
                    message += f" Details: {detail}"
                raise RuntimeError(message)

            self.last_error = None
            self.last_info["stage"] = "transcribed"
            self.last_info["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
            return text[:1200]
        except Exception as exc:
            self.last_info["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
            self.last_error = f"{type(exc).__name__}: {exc}"
            raise RuntimeError(f"Voice transcription failed: {exc}") from exc
