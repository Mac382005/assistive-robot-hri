from __future__ import annotations

from experiment.conditions import SocialCondition
from robot.audio import MockAudioController
from robot.leds import MockLEDController
from robot.servo import MockServoController


class MockHardwareController:
    """Coordinates mock hardware while developing on Windows."""

    def __init__(self) -> None:
        self.servo = MockServoController()
        self.leds = MockLEDController()
        self.audio = MockAudioController()

    @property
    def mode(self) -> str:
        return "MOCK"

    def begin_reminder(self, condition: SocialCondition, voice_message: str) -> list[str]:
        events: list[str] = []
        if condition.head_orientation:
            events.append(self.servo.turn_head("user"))
        if condition.led_indicator:
            events.append(self.leds.set_reminder_led(True))
        if condition.voice_reminder:
            events.append(self.audio.speak(voice_message))
        if condition.arm_gesture:
            events.append(self.servo.wave())
        return events

    def acknowledge(self, condition: SocialCondition) -> list[str]:
        events: list[str] = []
        if condition.acknowledgement:
            events.append(self.audio.acknowledgement())
        if condition.led_indicator:
            events.append(self.leds.set_reminder_led(False))
        return events

    def reset(self) -> list[str]:
        return [self.leds.reset(), self.servo.reset()]

    def test_action(self, action: str) -> str:
        actions = {
            "head_left": lambda: self.servo.turn_head("left"),
            "head_centre": lambda: self.servo.turn_head("centre"),
            "head_right": lambda: self.servo.turn_head("right"),
            "led_on": lambda: self.leds.set_reminder_led(True),
            "led_off": lambda: self.leds.set_reminder_led(False),
            "wave": self.servo.wave,
            "reset": lambda: "; ".join(self.reset()),
        }
        if action not in actions:
            raise ValueError("Unknown hardware test action.")
        return actions[action]()
