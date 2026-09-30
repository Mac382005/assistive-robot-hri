class MockServoController:
    """Windows-safe stand-in for the future Raspberry Pi servo controller."""

    def turn_head(self, position: str) -> str:
        position = position.lower()
        if position not in {"left", "centre", "right", "user"}:
            raise ValueError("Unsupported head position.")
        message = f"[MOCK SERVO] Head -> {position}"
        print(message)
        return message

    def wave(self) -> str:
        message = "[MOCK SERVO] Arm gesture -> wave"
        print(message)
        return message

    def reset(self) -> str:
        return self.turn_head("centre")
