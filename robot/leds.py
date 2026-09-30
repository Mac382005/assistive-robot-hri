class MockLEDController:
    """Windows-safe stand-in for future Raspberry Pi GPIO LEDs."""

    def set_reminder_led(self, enabled: bool) -> str:
        state = "ON" if enabled else "OFF"
        message = f"[MOCK LED] Reminder LED -> {state}"
        print(message)
        return message

    def reset(self) -> str:
        return self.set_reminder_led(False)
