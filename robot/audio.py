class MockAudioController:
    """
    Backend audio placeholder.

    Version 1 plays the development beep / speech from the browser so that the
    Windows prototype works without extra audio libraries. Later this class can
    be replaced with Raspberry Pi playback of fixed WAV files for experiments.
    """

    def speak(self, text: str) -> str:
        message = f"[MOCK AUDIO] Speak -> {text}"
        print(message)
        return message

    def acknowledgement(self) -> str:
        return self.speak("Thank you.")
