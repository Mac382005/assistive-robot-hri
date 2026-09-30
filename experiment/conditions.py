from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SocialCondition:
    name: str
    label: str
    face_animation: bool
    voice_reminder: bool
    head_orientation: bool
    personalised_greeting: bool
    acknowledgement: bool
    led_indicator: bool
    arm_gesture: bool = False

    @property
    def social_cue_count(self) -> int:
        """Count only the cues being treated as social cues in the experiment."""
        return sum(
            (
                self.face_animation,
                self.voice_reminder,
                self.head_orientation,
                self.personalised_greeting,
                self.acknowledgement,
                self.arm_gesture,
            )
        )

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["social_cue_count"] = self.social_cue_count
        return payload


LOW = SocialCondition(
    name="LOW",
    label="Low social cues",
    face_animation=False,
    voice_reminder=False,
    head_orientation=False,
    personalised_greeting=False,
    acknowledgement=False,
    led_indicator=False,
    arm_gesture=False,
)

HIGH = SocialCondition(
    name="HIGH",
    label="High social cues",
    face_animation=True,
    voice_reminder=True,
    head_orientation=True,
    personalised_greeting=True,
    acknowledgement=True,
    led_indicator=True,
    arm_gesture=False,
)

CONDITIONS = {"LOW": LOW, "HIGH": HIGH}


def get_condition(name: str) -> SocialCondition:
    key = (name or "").strip().upper()
    if key not in CONDITIONS:
        raise ValueError(f"Unknown experimental condition: {name!r}")
    return CONDITIONS[key]
