from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    v = _env(name, "1" if default else "0").lower()
    return v in ("1", "true", "yes", "on")


@dataclass
class Config:
    home: Path = field(default_factory=lambda: Path(_env("AIPET_HOME", "./pet_home")))
    site_url: str = field(default_factory=lambda: _env("AIPET_SITE_URL"))
    owner_email: str = field(default_factory=lambda: _env("AIPET_OWNER_EMAIL"))
    seed: int | None = field(default_factory=lambda: int(_env("AIPET_SEED")) if _env("AIPET_SEED") else None)

    # brain
    brain: str = field(default_factory=lambda: _env("AIPET_BRAIN", "auto"))  # auto | claude | instinct
    api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    model: str = field(default_factory=lambda: _env("AIPET_MODEL", "claude-opus-5-5"))
    effort: str = field(default_factory=lambda: _env("AIPET_EFFORT", "medium"))
    max_llm_calls_per_tick: int = field(default_factory=lambda: _env_int("AIPET_MAX_LLM_CALLS_PER_TICK", 6))

    # email
    email_address: str = field(default_factory=lambda: _env("AIPET_EMAIL_ADDRESS"))
    imap_host: str = field(default_factory=lambda: _env("AIPET_IMAP_HOST"))
    imap_port: int = field(default_factory=lambda: _env_int("AIPET_IMAP_PORT", 993))
    smtp_host: str = field(default_factory=lambda: _env("AIPET_SMTP_HOST"))
    smtp_port: int = field(default_factory=lambda: _env_int("AIPET_SMTP_PORT", 587))
    email_user: str = field(default_factory=lambda: _env("AIPET_EMAIL_USER"))
    email_password: str = field(default_factory=lambda: _env("AIPET_EMAIL_PASSWORD"))
    email_allowlist: list[str] = field(
        default_factory=lambda: [s.strip().lower() for s in _env("AIPET_EMAIL_ALLOWLIST").split(",") if s.strip()]
    )
    max_emails_per_day: int = field(default_factory=lambda: _env_int("AIPET_MAX_EMAILS_PER_DAY", 10))

    # shop
    currency: str = field(default_factory=lambda: _env("AIPET_CURRENCY", "usd").lower())
    stripe_secret_key: str = field(default_factory=lambda: _env("STRIPE_SECRET_KEY"))

    # misc
    research_enabled: bool = field(default_factory=lambda: _env_bool("AIPET_RESEARCH_ENABLED", True))
    growth_ticks: tuple[int, int, int] = (1, 4, 12)  # hatchling, juvenile, adult

    @property
    def site_dir(self) -> Path:
        return self.home / "site"

    @property
    def data_dir(self) -> Path:
        return self.home / "data"

    @property
    def creations_dir(self) -> Path:
        return self.home / "creations"

    @property
    def mail_dir(self) -> Path:
        return self.home / "mail"

    @property
    def has_real_mail(self) -> bool:
        return bool(self.email_address and self.imap_host and self.smtp_host and self.email_password)

    @property
    def pet_email(self) -> str:
        return self.email_address or "pet@localhost"

    def public_url(self, rel: str) -> str:
        base = self.site_url.rstrip("/")
        rel = rel.lstrip("/")
        return f"{base}/{rel}" if base else rel
