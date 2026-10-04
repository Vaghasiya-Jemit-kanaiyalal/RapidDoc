"""Units and aspect-ratio arithmetic for image sizing.

Both writers need the same three decisions - what unit is the number in, which
dimension wins when only one is given, and is the new box inside the page - so
they are resolved here once rather than separately per format. Getting that
subtly different between the DOCX and PDF paths is how "set the width to 4 inches"
ends up producing a 4-inch picture in one format and 4-scaled-cms in the other.

DOCX measures in EMU (914400 per inch). PDF content streams measure in points
(72 per inch). Everything user-facing arrives in one of the units below and is
converted at the edge.
"""

# EMU per unit. 914400 EMU = 1 inch = 2.54 cm at the ISO definition, and
# PowerPoint's 360000-per-cm is the rounded value Word itself writes, so both
# are used from the format that defines them.
EMU_PER_INCH = 914400
EMU_PER_CM = 360000
EMU_PER_MM = 36000
EMU_PER_PT = 12700
EMU_PER_PX = 9525  # 96 dpi, the CSS reference resolution

# Every unit is normalised to inches for the cross-checks below.
INCHES_PER_UNIT = {
    "px": EMU_PER_PX / EMU_PER_INCH,
    "pt": EMU_PER_PT / EMU_PER_INCH,
    "in": 1.0,
    "cm": EMU_PER_CM / EMU_PER_INCH,
    "mm": EMU_PER_MM / EMU_PER_INCH,
}

UNIT_LABELS = {
    "px": "px", "pt": "pt", "in": '"', "cm": "cm", "mm": "mm",
}

# A box larger than this is refused rather than written. Real documents never
# need it, and it is the cheapest guard against a typo like width=4000 turning
# into an image that no renderer will display.
MAX_DIMENSION_INCHES = 200.0


class ResizeError(ValueError):
    """A resize request that cannot be honoured, phrased for the user."""


def to_emu(value, unit: str) -> int:
    """Convert ``value`` in ``unit`` to EMU."""
    if unit not in INCHES_PER_UNIT:
        raise ResizeError(
            f'"{unit}" is not a size I understand. Use px, pt, in, cm or mm.'
        )
    return int(round(float(value) * INCHES_PER_UNIT[unit] * EMU_PER_INCH))


def to_points(value, unit: str) -> float:
    """Convert ``value`` in ``unit`` to PDF points."""
    return float(value) * INCHES_PER_UNIT[unit] * 72.0


def normalise_unit(unit) -> str:
    unit = (unit or "px").strip().lower()
    if unit in ("inches", "inch", '"'):
        unit = "in"
    elif unit in ("pixels", "pixel"):
        unit = "px"
    elif unit in ("points", "point"):
        unit = "pt"
    elif unit in ("centimetres", "centimeter"):
        unit = "cm"
    elif unit in ("millimetres", "millimeter"):
        unit = "mm"
    if unit not in INCHES_PER_UNIT:
        raise ResizeError(
            f'"{unit}" is not a size I understand. Use px, pt, in, cm or mm.'
        )
    return unit


def resolve_target_box(
    current_width_emu: int,
    current_height_emu: int,
    width=None,
    height=None,
    unit: str = "px",
    keep_aspect: bool = True,
) -> tuple:
    """The new box in EMU, as ``(width_emu, height_emu)``.

    Rules, chosen so that the common cases need no explanation:

    * one dimension given, aspect kept -> the other follows from the current
      ratio, so "make it 4in wide" does not silently squash the picture.
    * one dimension given, aspect not kept -> that dimension changes and the
      other is left alone.
    * both given, aspect kept -> width governs, because a locked ratio cannot
      satisfy two independent numbers and width is the one a user dragging a
      corner handle means.
    * both given, aspect free -> both are applied exactly.

    ``keep_aspect`` defaults to True because distorting a logo is almost never
    intended and is very hard to notice in a thumbnail.
    """
    unit = normalise_unit(unit)
    has_w = width is not None
    has_h = height is not None

    if not has_w and not has_h:
        raise ResizeError("Give a width, a height, or both.")

    for label, value in (("width", width), ("height", height)):
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ResizeError(f"The {label} has to be a number, not {value!r}.")
        if number <= 0:
            raise ResizeError(f"The {label} has to be greater than zero.")
        if number * INCHES_PER_UNIT[unit] > MAX_DIMENSION_INCHES:
            raise ResizeError(
                f"A {number:g}{UNIT_LABELS[unit]} {label} is larger than this "
                "application allows."
            )

    if current_width_emu <= 0 or current_height_emu <= 0:
        raise ResizeError(
            "This image has no readable size in the document, so it cannot be "
            "resized. Replace it instead."
        )

    ratio = current_height_emu / current_width_emu

    if has_w and has_h:
        if keep_aspect:
            new_w = to_emu(width, unit)
            return new_w, int(round(new_w * ratio))
        return to_emu(width, unit), to_emu(height, unit)

    if has_w:
        new_w = to_emu(width, unit)
        return new_w, int(round(new_w * ratio)) if keep_aspect else current_height_emu

    new_h = to_emu(height, unit)
    return int(round(new_h / ratio)) if keep_aspect else current_width_emu, new_h


def describe_change(old_w, old_h, new_w, new_h) -> str:
    """A one-line summary of a resize, for the toast and the audit log."""
    def fmt(emu):
        return f"{emu / EMU_PER_INCH:.2f}\""

    if old_w == new_w and old_h == new_h:
        return f"already {fmt(new_w)} x {fmt(new_h)}"
    return f"{fmt(old_w)} x {fmt(old_h)} -> {fmt(new_w)} x {fmt(new_h)}"