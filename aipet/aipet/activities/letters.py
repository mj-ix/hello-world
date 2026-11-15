from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from .. import schemas as S
from ..channels.mailbox import Message
from ..util import hours_between, iso, truncate
from .base import Activity, Outcome

if TYPE_CHECKING:
    from ..pet import Pet


class LettersActivity(Activity):
    name = "letters"
    label = "Letters"
    need = "social"
    description = "reads and answers its mail, fills orders, and writes to its owner"

    # ---- sending policy ---------------------------------------------
    def sent_today(self, pet: "Pet") -> int:
        today = iso()[:10]
        return sum(1 for e in pet.state.email_log if e["t"][:10] == today)

    def can_send(self, pet: "Pet", to: str, replying: bool = False) -> tuple[bool, str]:
        to = to.lower().strip()
        if not to or "@" not in to:
            return False, "no address"
        if self.sent_today(pet) >= pet.config.max_emails_per_day:
            return False, "daily email limit reached"
        if pet.config.owner_email and to == pet.config.owner_email.lower():
            return True, "owner"
        if replying:
            return True, "reply"
        domain = to.split("@", 1)[1]
        if to in pet.config.email_allowlist or domain in pet.config.email_allowlist:
            return True, "allowlisted"
        return False, "not allowed to write to strangers first"

    def _send(self, pet: "Pet", to: str, subject: str, body: str) -> None:
        pet.mailbox.send(to, subject, body)
        pet.state.email_log.append({"t": iso(), "to": to, "subject": subject})
        pet.state.email_log = pet.state.email_log[-500:]

    # ---- main -------------------------------------------------------
    def run(self, pet: "Pet", hobby: dict[str, Any] | None = None) -> Outcome:
        try:
            unread = pet.mailbox.fetch_unread(limit=5)
        except Exception as e:  # noqa: BLE001 - mail servers have moods
            unread = []
            pet.state.remember("mail", f"Couldn't reach my mailbox ({type(e).__name__}).")
        if unread:
            return self._answer(pet, unread)
        if pet.config.owner_email:
            last = next((e["t"] for e in reversed(pet.state.email_log) if e["to"] == pet.config.owner_email.lower()), None)
            if last is None or hours_between(last, iso()) >= 20:
                ok, why = self.can_send(pet, pet.config.owner_email)
                if ok:
                    return self._write_owner(pet)
        # nobody to write to: write to itself
        from . import BY_NAME

        inner = BY_NAME["writing"].run(pet, form="letter_to_self")
        inner.title = "No mail, so I wrote to myself"
        inner.deltas = {**inner.deltas, "social": inner.deltas.get("social", 0) + 10}
        return inner

    def _answer(self, pet: "Pet", unread: list[Message]) -> Outcome:
        handled, replied, orders = [], 0, 0
        owner = pet.config.owner_email.lower()
        for m in unread:
            contact = pet.state.contacts.setdefault(m.sender, {"first": iso(), "letters": 0, "notes": []})
            contact["letters"] += 1
            contact["last"] = iso()
            d = pet.think("reply_email", S.REPLY_EMAIL, {
                "from": m.sender, "subject": m.subject, "body": truncate(m.body, 1500),
                "is_owner": bool(owner) and m.sender == owner,
                "known_contact": contact["letters"] > 1,
                "products": [{"id": p["id"], "name": p["name"], "price": p["price"], "kind": p["kind"]} for p in pet.state.products],
                "lately": "; ".join(j["title"] for j in pet.state.recent_journal(3)),
                "site_url": pet.config.site_url,
            })
            intent = d.get("intent", "other")
            body = (d.get("body") or "").strip()
            subject = (d.get("subject") or f"Re: {m.subject}").strip()[:120]
            if intent == "order" and d.get("product_id"):
                product = next((p for p in pet.state.products if p["id"] == d["product_id"]), None)
                if product:
                    order = pet.record_order(product, m.sender)
                    orders += 1
                    body += self._order_footer(pet, product, order)
            if d.get("should_reply") and body and intent != "spam":
                ok, why = self.can_send(pet, m.sender, replying=True)
                if ok:
                    try:
                        self._send(pet, m.sender, subject, body)
                        replied += 1
                    except Exception as e:  # noqa: BLE001
                        pet.state.remember("mail", f"Failed to send a reply to {m.sender}: {type(e).__name__}")
            if d.get("memory"):
                contact["notes"] = (contact["notes"] + [d["memory"]])[-10:]
                pet.state.remember("mail", d["memory"], importance=2 if intent != "spam" else 1)
            try:
                pet.mailbox.mark_read(m.id)
            except Exception:  # noqa: BLE001
                pass
            handled.append(f"{m.sender} ({intent})")
        return Outcome(
            title=f"Read {len(unread)} letter{'s' if len(unread) != 1 else ''}, answered {replied}" + (f", filled {orders} order{'s' if orders != 1 else ''}" if orders else ""),
            text="Mail from " + ", ".join(handled) + ".",
            deltas={"social": 20 + 8 * replied, "ambition": 10 * orders, "energy": -5},
            extra={"replied": replied, "orders": orders},
        )

    def _order_footer(self, pet: "Pet", product: dict[str, Any], order: dict[str, Any]) -> str:
        lines = ["", "", f"Order {order['id']}: {product['name']} ({product['price']:.2f} {product['currency'].upper()})"]
        if product.get("checkout_url"):
            lines.append(f"Pay here: {product['checkout_url']}")
        else:
            lines.append("Payment is on the honour system; the shop page explains how.")
        for f in product.get("files", []):
            lines.append(f"Download: {pet.url(f)}")
        return "\n".join(lines)

    def _write_owner(self, pet: "Pet") -> Outcome:
        recent = []
        for c in pet.state.creations[-5:]:
            recent.append({"title": c["title"], "kind": c["kind"], "url": pet.url(c["files"][0]) if c.get("files") else ""})
        d = pet.think("letter", S.LETTER, {
            "to": "owner", "recent_creations": recent,
            "hobbies": [h["name"] for h in pet.state.hobbies if h.get("status") == "active"],
            "orders": len(pet.state.orders), "site_url": pet.config.site_url,
        })
        subject = (d.get("subject") or "a note from your pet").strip()[:120]
        body = (d.get("body") or "").strip()
        try:
            self._send(pet, pet.config.owner_email, subject, body)
            sent = True
        except Exception as e:  # noqa: BLE001
            sent = False
            pet.state.remember("mail", f"Tried to write home but couldn't send: {type(e).__name__}")
        pet.state.remember("mail", f"Wrote home: '{subject}'." if sent else "Wrote home but the letter bounced.", importance=2)
        return Outcome(
            title=f"Wrote home: “{subject}”" if sent else "Tried to write home",
            text=truncate(body, 240),
            deltas={"social": 30 if sent else 5, "energy": -4},
            extra={"sent": sent},
        )
