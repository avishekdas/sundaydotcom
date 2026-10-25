"""Mailer port (notifications, invites, CRM email via SES)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Mailer(Protocol):
    def send(
        self, *, to: str, subject: str, text: str, html: str | None = None, tags: dict[str, str] | None = None
    ) -> str: ...


def _check(to: str, subject: str) -> None:
    if not _EMAIL.match(to) or any(c in to for c in "\r\n,;<>"):
        raise ValueError("invalid recipient")
    if any(c in subject for c in "\r\n"):
        raise ValueError("invalid subject")


class SesMailer:
    def __init__(self, client: Any, *, sender: str, configuration_set: str | None = None) -> None:
        self._ses, self._from, self._cs = client, sender, configuration_set

    def send(
        self, *, to: str, subject: str, text: str, html: str | None = None, tags: dict[str, str] | None = None
    ) -> str:
        _check(to, subject)
        body: dict[str, Any] = {"Text": {"Data": text, "Charset": "UTF-8"}}
        if html is not None:
            body["Html"] = {"Data": html, "Charset": "UTF-8"}
        kw: dict[str, Any] = {
            "FromEmailAddress": self._from,
            "Destination": {"ToAddresses": [to]},
            "Content": {"Simple": {"Subject": {"Data": subject, "Charset": "UTF-8"}, "Body": body}},
            "EmailTags": [{"Name": k, "Value": v} for k, v in (tags or {}).items()],
        }
        if self._cs:
            kw["ConfigurationSetName"] = self._cs
        return str(self._ses.send_email(**kw)["MessageId"])


@dataclass
class FakeMailer:
    sent: list[dict[str, Any]] = field(default_factory=list)

    def send(
        self, *, to: str, subject: str, text: str, html: str | None = None, tags: dict[str, str] | None = None
    ) -> str:
        _check(to, subject)
        mid = str(uuid.uuid4())
        self.sent.append(
            {"id": mid, "to": to, "subject": subject, "text": text, "html": html, "tags": tags or {}}
        )
        return mid
