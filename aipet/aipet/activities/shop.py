from __future__ import annotations

import shutil
import zipfile
from typing import TYPE_CHECKING, Any

from .. import schemas as S
from ..state import new_id
from ..util import iso, slugify
from .base import Activity, Outcome

if TYPE_CHECKING:
    from ..pet import Pet

SELLABLE = ("music", "art", "writing", "world")


class ShopActivity(Activity):
    name = "shop"
    label = "Shopkeeping"
    need = "ambition"
    min_stage = "juvenile"
    description = "turns its creations into products and keeps its storefront stocked"

    def available(self, pet: "Pet") -> bool:
        return super().available(pet) and len([c for c in pet.state.creations if c["kind"] in SELLABLE]) >= 2

    def run(self, pet: "Pet", hobby: dict[str, Any] | None = None) -> Outcome:
        sold_ids = {cid for p in pet.state.products for cid in p["creation_ids"]}
        pool = [c for c in pet.state.creations if c["kind"] in SELLABLE and c["id"] not in sold_ids][-12:]
        if len(pool) < 1:
            return self._inventory(pet)
        d = pet.think("design_product", S.DESIGN_PRODUCT, {
            "creations": [{"id": c["id"], "kind": c["kind"], "title": c["title"]} for c in pool],
            "existing_products": [{"name": p["name"], "kind": p["kind"], "price": p["price"]} for p in pet.state.products[-6:]],
            "currency": pet.config.currency,
            "orders_so_far": len(pet.state.orders),
        })
        by_id = {c["id"]: c for c in pool}
        chosen = [by_id[i] for i in d.get("creation_ids", []) if i in by_id] or pool[-1:]
        kind = d.get("kind") if d.get("kind") in S.PRODUCT_KINDS else "bundle"
        name = (d.get("name") or f"{kind} by {pet.state.name}").strip()[:60]
        price = round(max(1.0, min(200.0, float(d.get("price", 5)))), 2)
        slug = slugify(name)
        folder = pet.config.creations_dir / "products" / slug
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
        files: list[str] = []
        all_src = [pet.config.home / f for c in chosen for f in c["files"]]
        all_src = [p for p in all_src if p.exists()]
        if len(all_src) == 1 and all_src[0].suffix in (".svg", ".md", ".wav", ".mid"):
            dst = folder / all_src[0].name
            shutil.copy2(all_src[0], dst)
            files.append(pet.rel(dst))
        else:
            zpath = folder / f"{slug}.zip"
            with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
                for p in all_src:
                    z.write(p, arcname=f"{slug}/{p.parent.name}/{p.name}")
                z.writestr(f"{slug}/README.txt", f"{name}\n{d.get('tagline', '')}\n\n{d.get('description', '')}\n\nMade by {pet.state.name}, a {pet.state.species}.\n")
            files.append(pet.rel(zpath))
        preview = next((f for c in chosen for f in c["files"] if f.endswith(".svg")), None)
        product = {
            "id": new_id("prod"), "name": name, "kind": kind, "tagline": d.get("tagline", ""), "description": d.get("description", ""),
            "price": price, "currency": pet.config.currency, "creation_ids": [c["id"] for c in chosen], "files": files,
            "preview": preview, "checkout_url": None, "t": iso(), "tick": pet.state.ticks,
        }
        if pet.payments is not None:
            try:
                product["checkout_url"] = pet.payments.create_payment_link(name, product["description"], price, pet.config.currency, pet.url("shop.html"))
            except Exception as e:  # noqa: BLE001
                pet.state.remember("shop", f"Couldn't set up checkout for {name}: {type(e).__name__}.")
        pet.state.products.append(product)
        pet.state.remember("shop", f"Put '{name}' in the shop for {price:.2f} {pet.config.currency.upper()}.", importance=2)
        how = "with a real checkout link" if product["checkout_url"] else "on the honour system"
        return Outcome(
            title=f"New in the shop: “{name}”",
            text=f"{d.get('tagline', '')} {d.get('description', '')} Priced at {price:.2f} {pet.config.currency.upper()}, {how}.",
            deltas={"ambition": 35, "energy": -10, "expression": 5},
            extra={"product_id": product["id"]},
        )

    def _inventory(self, pet: "Pet") -> Outcome:
        n = len(pet.state.products)
        o = len(pet.state.orders)
        pet.state.remember("shop", f"Took inventory: {n} products, {o} orders.")
        return Outcome(
            title="Took inventory",
            text=f"{n} product{'s' if n != 1 else ''} on the shelf, {o} order{'s' if o != 1 else ''} so far. Nothing new to list yet; I should make more things.",
            deltas={"ambition": 12, "expression": -5},
        )
