"""Human-readable ``changelog.comment`` text for HVAC changes.

The `changelog` table is the audit trail for manual HVAC changes. Its
`current_values`/`new_value` columns hold raw AE-200 values -- integer wire codes
for drive and fan speed, non-canonical strings for set points -- so the comment is
what makes a row readable without a lookup table. Format is
``<what changed> <old> -> <new>``.

Kept out of `rules_engine` so the command paths there read as control flow, and so
this prose is testable on its own.
"""


def change_comment(label: str, current, new, names: dict[int, str] | None = None) -> str:
    """Describe one HVAC change in words, for the changelog audit trail.

    Pass ``names`` for changes logged as wire codes (drive, fan speed).
    """
    if names is not None:
        current, new = names.get(current, current), names.get(new, new)
    return f"{label} {current} -> {new}"


def temp_label(value: float | None) -> str:
    """Render one set point for a changelog comment.

    Always goes through the parsed float, so a unit reporting "24" and one
    reporting "24.0" describe an identical change identically. A unit that has
    never run in the relevant mode reports no set point at all.
    """
    return "unknown" if value is None else f"{value:g}"


def auto_temps_label(heat: float | None, cool: float | None) -> str:
    """Render an Auto-mode setpoint pair for a changelog comment."""
    return f"Heat={temp_label(heat)} Cool={temp_label(cool)}"
