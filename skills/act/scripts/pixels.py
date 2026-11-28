"""Read ACT's day grid from a screenshot (standard library only).

ACT draws each exchange's day grid without exposing it to accessibility: the cells are not in
the uiautomator dump. So the grid is read from the screen's pixels: the top row is you (green
cells), the bottom row is the partner (blue cells, filled or light), today's date is the green one above the grid.
Colours are ACT's dark theme; with any other look nothing is found and the card is reported as
"can't tell", never as "not opened".
"""
import struct, zlib

ME = (61, 220, 151)          # green cell: you opened their app that day
THEM = (107, 181, 255)       # blue cell: they opened yours that day
EMPTY = ((29, 36, 45), (24, 29, 37))     # a day without an open (past, future)
CHECK_SHADES = ((6, 34, 61), (12, 59, 40), (6, 40, 27))   # the check marks drawn inside cells


def load(data):
    """Decode a PNG (8-bit RGB/RGBA, as `screencap -p` writes it) into (width, height, bpp, rows)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    i, idat = 8, b""
    while i < len(data):
        n, typ = struct.unpack(">I4s", data[i:i + 8])
        body = data[i + 8:i + 8 + n]
        i += 12 + n
        if typ == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", body[:10])
            assert depth == 8 and ctype in (2, 6), "unexpected PNG format"
        elif typ == b"IDAT":
            idat += body
    bpp = 4 if ctype == 6 else 3
    raw, stride = zlib.decompress(idat), w * bpp
    rows, prev, p = [], bytearray(stride), 0
    for _ in range(h):
        f, line = raw[p], bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if f == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 255
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                line[x] = (line[x] + ((line[x - bpp] if x >= bpp else 0) + prev[x]) // 2) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                b, c = prev[x], prev[x - bpp] if x >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    return w, h, bpp, rows


def from_raw(data):
    """A raw `screencap` (no -p) as (width, height, bpp, rows), like load() but with nothing to decode."""
    w, h = struct.unpack("<II", data[:8])
    head = len(data) - w * h * 4
    assert head in (12, 16), "not a raw screencap"
    return w, h, 4, [data[head + y * w * 4:head + (y + 1) * w * 4] for y in range(h)]


def _near(p, q, d=2):
    return abs(p[0] - q[0]) <= d and abs(p[1] - q[1]) <= d and abs(p[2] - q[2]) <= d


def _green(p):
    return p[1] > 150 and p[1] - p[0] > 80 and p[1] - p[2] > 30


def _blue(p):
    return p[2] > 170 and p[0] < 140 and p[2] - p[0] > 80


def _cell(p):
    return _green(p) or _blue(p) or any(_near(p, c) for c in EMPTY + CHECK_SHADES)


def read_grid(img, box):
    """Today's cells of the grid inside `box` (a card's bounds, clipped to the screen).
    Returns {"me": bool, "them": bool, "them_yesterday": bool or None (today is the first day)},
    or None when no two-row grid with a today column is found."""
    w, h, bpp, rows = img
    l, t, r, b = box
    px = lambda x, y: rows[y][x * bpp:x * bpp + 3]
    xs = range(max(l + 120, 0), min(r - 20, w), 2)
    if not xs:
        return None
    full = [sum(1 for x in xs if _cell(px(x, y))) > len(xs) * 0.55 for y in range(max(t, 0), min(b, h))]
    bands, start = [], None
    for i, on in enumerate(full + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if i - start >= 25:
                bands.append((max(t, 0) + start, max(t, 0) + i))
            start = None
    if len(bands) < 2 or bands[1][0] - bands[0][1] > 30:
        return None  # one row only: the partner's row is outlined ("auto-check off") or cut off
    (t1, b1), (t2, b2) = bands[:2]
    today = [x for y in range(max(t1 - 70, 0), t1 - 8) for x in xs if _green(px(x, y))]
    if not today:
        return None
    tx = sum(today) // len(today)
    def share(test, y1, y2):  # whole cell: a filled one, or a light one (outline + check, "opened manually")
        cells = [px(x, y) for x in range(tx - 24, tx + 25, 2) for y in range(y1, y2, 2)]
        return sum(map(test, cells)) / max(len(cells), 1)
    out = {"me": share(_green, t1, b1) > 0.05, "them": share(_blue, t2, b2) > 0.05, "them_yesterday": None}
    # yesterday: the cell left of today's, found as runs of cell colour across both rows' middles
    m1, m2 = (t1 + b1) // 2, (t2 + b2) // 2
    on = [x for x in range(max(l, 0), min(r, w)) if _cell(px(x, m1)) or _cell(px(x, m2))]
    runs = []
    for x in on:
        if runs and x - runs[-1][1] <= 3:
            runs[-1][1] = x
        else:
            runs.append([x, x])
    i = next((k for k, (a, z) in enumerate(runs) if a - 6 <= tx <= z + 6), None)
    if i:  # today isn't the grid's first day
        a, z = runs[i - 1]
        if z - a >= 20:
            cells = [px(x, y) for x in range(a + 3, z - 2, 2) for y in range(t2, b2, 2)]
            out["them_yesterday"] = sum(map(_blue, cells)) / max(len(cells), 1) > 0.05
    return out


SNACKBAR = (29, 36, 45)      # ACT's snackbar: a slate bar across the width, over list, cards or ads


def raw_bar_rows(data, y_from, y_to, color=SNACKBAR):
    """From a raw `screencap` (no -p: fast, no PNG to decode), the rows between two heights that are
    `color` across almost the whole width (ACT's snackbar; no list row is one flat colour edge to edge)."""
    n = len(data)
    if n < 16:
        return set()
    w, h = struct.unpack("<II", data[:8])
    head = n - w * h * 4
    if head not in (12, 16) or w <= 0:
        return set()
    rows, xs = set(), range(w // 15, w - w // 15, 8)
    for y in range(max(y_from, 0), min(y_to, h), 3):
        base = head + y * w * 4
        hit = sum(1 for x in xs if _near(data[base + 4 * x:base + 4 * x + 3], color))
        if hit > len(xs) * 0.9:
            rows.add(y)
    return rows
