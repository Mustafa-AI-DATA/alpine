"""Deterministic PQA / KPT tariff rules and cost calculator.

Rates sourced from: Port Tariiff of PQA & KPT.xls (effective 02-06-2023).
Published slabs are GRT-based. NRT is accepted as input but calculations use GRT
unless the user only provides NRT (then we note the limitation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

EFFECTIVE_DATE = "02-06-2023"
SST_RATE = 0.13  # Sindh Sales Tax on above charges from 01-07-2016

# Port Qasim pilotage: rate per GRT for inward/outward (each direction uses same rate)
PQA_PILOTAGE_SLABS: list[tuple[float, float | None, float]] = [
    # (min_grt_inclusive, max_grt_inclusive_or_None, rate_per_grt)
    (200, 4000, 0.75),
    (4001, 5000, 0.60),
    (5001, 6000, 0.55),
    (6001, 7000, 0.50),
    (7001, 10000, 0.43),
    (10001, 15000, 0.36),
    (15001, 20000, 0.32),
    (20001, 30000, 0.29),
    (30001, 40000, 0.26),
    (40001, 50000, 0.25),
    (50001, None, 0.24),
]

# Karachi pilotage: $0.14/GRT inward & $0.14/GRT outward, min $700 each way (all GRT bands same)
KPT_PILOTAGE_PER_GRT = 0.14
KPT_PILOTAGE_MIN = 700.0

# Berth fee
PQA_BERTH_PER_GRT_DAY = 0.08
PQA_BERTH_MIN = 300.0

KPT_BERTH_SLABS: list[tuple[float, float | None, float]] = [
    (0, 5000, 0.084),
    (5001, 25000, 0.112),
    (25001, 45000, 0.14),
    (45001, 90000, 0.135),
    (90001, None, 0.13),
]
KPT_BERTH_MIN = 315.0

# Port dues (per call)
PQA_PORT_DUES_PER_GRT = 0.30
KPT_PORT_DUES_SLABS: list[tuple[float, float | None, float]] = [
    (0, 5000, 0.28),
    (5001, 25000, 0.364),
    (25001, 45000, 0.392),
    (45001, 90000, 0.378),
    (90001, None, 0.364),
]

# Anchorage
PQA_ANCHORAGE_PER_GRT_DAY = 0.013
KPT_ANCHORAGE_PER_GRT_DAY = 0.021

# Other fixed
PQA_PIPELINE_PER_DAY = 105.0
KPT_PIPELINE_PER_DAY = 120.0
PQA_CANCEL = 300.0
KPT_CANCEL = 420.0
KPT_TUG_IN = 3600.0  # 2 tugs inward 1 hour
KPT_TUG_OUT = 3600.0
PQA_NIGHT_ESCORT_TUG = 900.0
KPT_PILOT_BOAT_IN = 140.0
KPT_PILOT_BOAT_OUT = 140.0


def _slab_rate(grt: float, slabs: list[tuple[float, float | None, float]]) -> float:
    for lo, hi, rate in slabs:
        if grt >= lo and (hi is None or grt <= hi):
            return rate
    return slabs[-1][2]


def _normalize_port(port: str | None) -> str:
    if not port:
        return "Port Qasim"
    p = port.lower()
    if "karachi" in p or "kpt" in p:
        return "Karachi"
    return "Port Qasim"


@dataclass
class LineItem:
    name: str
    amount: float
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "amount": round(self.amount, 2), "detail": self.detail}


def calculate_charges(
    *,
    port: str | None,
    grt: float | None,
    nrt: float | None = None,
    days: float | None = None,
    include: list[str] | None = None,
    apply_sst: bool = True,
    both_ways_pilotage: bool = True,
) -> dict[str, Any]:
    """Compute selected port charges with step-by-step breakdown."""
    notes: list[str] = []
    if grt is None and nrt is not None:
        notes.append(
            "Published tariff slabs are GRT-based. Only NRT was provided; "
            "no GRT→NRT conversion is in the tariff file, so calculation cannot be completed with NRT alone."
        )
        return {
            "ok": False,
            "error": "GRT required for published PQA/KPT tariff slabs. NRT alone is not sufficient.",
            "notes": notes,
            "effective_date": EFFECTIVE_DATE,
            "source": "Port Tariiff of PQA & KPT.xls",
        }
    if grt is None:
        return {
            "ok": False,
            "error": "GRT is required to calculate tariff (e.g. GRT=25000, days=3, port=Port Qasim).",
            "notes": notes,
            "effective_date": EFFECTIVE_DATE,
            "source": "Port Tariiff of PQA & KPT.xls",
        }

    port_name = _normalize_port(port)
    days = float(days or 1)
    include = [i.lower() for i in (include or ["berth", "anchorage", "port_dues", "pilotage"])]

    # Auto-include common items if user said "charges" / "cost" without specifics
    if not include:
        include = ["berth", "port_dues", "pilotage"]

    lines: list[LineItem] = []

    if any(x in include for x in ("berth", "berthing", "all")):
        if port_name == "Port Qasim":
            raw = grt * PQA_BERTH_PER_GRT_DAY * days
            amt = max(raw, PQA_BERTH_MIN) if days >= 1 else raw
            # minimum is per day practice: apply min against daily*days as sheet shows min $300
            amt = max(grt * PQA_BERTH_PER_GRT_DAY * days, PQA_BERTH_MIN)
            lines.append(
                LineItem(
                    "Berth Fee",
                    amt,
                    f"PQA ${PQA_BERTH_PER_GRT_DAY}/GRT/day × {grt} GRT × {days} days "
                    f"= ${grt * PQA_BERTH_PER_GRT_DAY * days:.2f}, minimum ${PQA_BERTH_MIN}",
                )
            )
        else:
            rate = _slab_rate(grt, KPT_BERTH_SLABS)
            raw = grt * rate * days
            amt = max(raw, KPT_BERTH_MIN)
            lines.append(
                LineItem(
                    "Berth Fee",
                    amt,
                    f"KPT ${rate}/GRT/day × {grt} GRT × {days} days "
                    f"= ${raw:.2f}, minimum ${KPT_BERTH_MIN}",
                )
            )

    if any(x in include for x in ("anchorage", "outer anchorage", "all")):
        rate = PQA_ANCHORAGE_PER_GRT_DAY if port_name == "Port Qasim" else KPT_ANCHORAGE_PER_GRT_DAY
        amt = grt * rate * days
        lines.append(
            LineItem(
                "Outer Anchorage Fee",
                amt,
                f"{port_name} ${rate}/GRT/day × {grt} GRT × {days} days = ${amt:.2f}",
            )
        )

    if any(x in include for x in ("port_dues", "port dues", "dues", "all")):
        if port_name == "Port Qasim":
            amt = grt * PQA_PORT_DUES_PER_GRT
            lines.append(
                LineItem(
                    "Port Dues (per call)",
                    amt,
                    f"PQA ${PQA_PORT_DUES_PER_GRT}/GRT/call × {grt} GRT = ${amt:.2f}",
                )
            )
        else:
            rate = _slab_rate(grt, KPT_PORT_DUES_SLABS)
            amt = grt * rate
            lines.append(
                LineItem(
                    "Port Dues (per call)",
                    amt,
                    f"KPT ${rate}/GRT/call × {grt} GRT = ${amt:.2f} (applicable from 30-06-2023)",
                )
            )

    if any(x in include for x in ("pilotage", "pilot", "all")):
        if port_name == "Port Qasim":
            rate = _slab_rate(grt, PQA_PILOTAGE_SLABS)
            one_way = grt * rate
            if both_ways_pilotage:
                amt = one_way * 2
                detail = (
                    f"PQA ${rate}/GRT inward/outward × {grt} GRT = ${one_way:.2f} one way; "
                    f"inward+outward = ${amt:.2f}"
                )
            else:
                amt = one_way
                detail = f"PQA ${rate}/GRT × {grt} GRT (one way) = ${amt:.2f}"
            lines.append(LineItem("Pilotage", amt, detail))
            notes.append(
                "PQA adds 5% on pilotage slabs from 16 May to 15 Sep each year (not applied unless season specified)."
            )
        else:
            one_way = max(grt * KPT_PILOTAGE_PER_GRT, KPT_PILOTAGE_MIN)
            amt = one_way * 2 if both_ways_pilotage else one_way
            detail = (
                f"KPT ${KPT_PILOTAGE_PER_GRT}/GRT (min ${KPT_PILOTAGE_MIN}) per direction; "
                f"one way ${one_way:.2f}"
                + (f"; inward+outward ${amt:.2f}" if both_ways_pilotage else "")
            )
            lines.append(LineItem("Pilotage", amt, detail))

    if any(x in include for x in ("tug", "tugs", "all")) and port_name == "Karachi":
        amt = KPT_TUG_IN + KPT_TUG_OUT
        lines.append(
            LineItem(
                "Tugs Hire",
                amt,
                f"KPT ${KPT_TUG_IN} inward (2 tugs) + ${KPT_TUG_OUT} outward (2 tugs) for 1 hour each",
            )
        )
    elif any(x in include for x in ("tug", "tugs")) and port_name == "Port Qasim":
        notes.append("PQA tug hire is listed as Nil in the General Port Tariff sheet.")

    if any(x in include for x in ("pipeline", "all")):
        rate = PQA_PIPELINE_PER_DAY if port_name == "Port Qasim" else KPT_PIPELINE_PER_DAY
        amt = rate * days
        lines.append(
            LineItem("Port Pipeline Charges", amt, f"{port_name} ${rate}/day × {days} days = ${amt:.2f}")
        )

    if nrt is not None:
        notes.append(f"NRT={nrt} was provided for reference; amounts below are calculated on GRT={grt}.")

    subtotal = sum(l.amount for l in lines)
    sst = subtotal * SST_RATE if apply_sst and lines else 0.0
    total = subtotal + sst

    if apply_sst and lines:
        lines.append(
            LineItem(
                "Sindh Sales Tax (13%)",
                sst,
                f"13% × subtotal ${subtotal:.2f} (from 01-07-2016)",
            )
        )

    return {
        "ok": True,
        "port": port_name,
        "grt": grt,
        "nrt": nrt,
        "days": days,
        "effective_date": EFFECTIVE_DATE,
        "source": "Port Tariiff of PQA & KPT.xls",
        "currency": "USD",
        "line_items": [l.as_dict() for l in lines],
        "subtotal": round(subtotal, 2),
        "sst": round(sst, 2),
        "total": round(total, 2),
        "notes": notes,
    }


def format_calculation(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return result.get("error") or "Calculation failed."
    inputs = f"GRT={result['grt']}"
    if result.get("nrt") is not None:
        inputs += f", NRT={result['nrt']}"
    inputs += f", days={result['days']}"
    lines = [
        f"**Estimated total: ${result['total']:.2f} USD** — {result['port']} "
        f"(tariff effective {result['effective_date']}; inputs {inputs})",
        "",
        "**Breakdown**",
    ]
    for item in result["line_items"]:
        lines.append(f"- **{item['name']}:** ${item['amount']:.2f} — {item['detail']}")
    lines.append(f"- Subtotal: ${result['subtotal']:.2f}")
    if result.get("sst"):
        lines.append(f"- SST 13%: ${result['sst']:.2f}")
    lines.append(f"- **Total: ${result['total']:.2f} USD**")
    if result.get("notes"):
        lines.append("")
        lines.append("**Notes**")
        for n in result["notes"]:
            lines.append(f"- {n}")
    lines.append("")
    lines.append(
        "**Assumption:** estimate from published General Port Tariff; confirm with ops for PDA/final billing."
    )
    lines.append(f"**Source:** {result['source']}")
    return "\n".join(lines)


def detect_charge_types(question: str) -> list[str]:
    q = question.lower()
    found: list[str] = []
    mapping = [
        ("berth", ("berth", "berthing")),
        ("anchorage", ("anchorage",)),
        ("port_dues", ("port dues", "port due", "dues")),
        ("pilotage", ("pilotage", "pilot")),
        ("tug", ("tug",)),
        ("pipeline", ("pipeline",)),
    ]
    for key, words in mapping:
        if any(w in q for w in words):
            found.append(key)
    if not found and any(w in q for w in ("tariff", "charges", "cost", "calculate", "rate")):
        found = ["berth", "anchorage", "port_dues", "pilotage"]
    return found
