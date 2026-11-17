"""Patient message templates.

Only the fields in ``MessageFields`` can appear in a message: practice and branch
names, date and time, the booking reference, a phone number and a portal link.
Appointment type, practitioner, notes and anything clinical are deliberately not
available to templates (rule 7): an appointment type such as "HIV counselling" or a
specialist's name can itself disclose health information to whoever sees the phone.
"""

from dataclasses import dataclass
from string import Template


@dataclass(frozen=True)
class MessageFields:
    practice: str
    branch: str
    date: str  # "Wednesday 18 Nov 2026"
    time: str  # "09:00"
    reference: str
    practice_phone: str
    # " or visit https://…/book/slug" when the portal is enabled, otherwise "".
    portal_suffix: str

    def as_dict(self) -> dict[str, str]:
        return {k: str(v) for k, v in self.__dict__.items()}


SUBJECTS = {
    "appointment_confirmed": "Appointment confirmed: $practice",
    "appointment_requested": "Appointment request received: $practice",
    "appointment_rescheduled": "Appointment moved: $practice",
    "appointment_cancelled": "Appointment cancelled: $practice",
    "appointment_reminder": "Appointment reminder: $practice",
}

BODIES = {
    "appointment_confirmed": (
        "$practice: your appointment is confirmed for $date at $time, $branch. "
        "Ref $reference. To change it, call $practice_phone$portal_suffix."
    ),
    "appointment_requested": (
        "$practice: we received your request for $date at $time, $branch. "
        "We will confirm shortly. Ref $reference."
    ),
    "appointment_rescheduled": (
        "$practice: your appointment has moved to $date at $time, $branch. Ref $reference."
    ),
    "appointment_cancelled": (
        "$practice: your appointment on $date at $time has been cancelled. "
        "Ref $reference. To rebook, call $practice_phone$portal_suffix."
    ),
    "appointment_reminder": (
        "Reminder from $practice: appointment on $date at $time, $branch. Ref $reference. "
        "Can't make it? Call $practice_phone."
    ),
}


def render(event_type: str, fields: MessageFields) -> tuple[str, str]:
    values = fields.as_dict()
    subject = Template(SUBJECTS[event_type]).substitute(values)
    body = Template(BODIES[event_type]).substitute(values)
    return subject, " ".join(body.split())
