# message_styles.py
import random
import datetime
import binascii
import os

# ==========================================
# Minimalist message style generator
# ==========================================

TEMPLATES = [
    # --- 0: Clean Minimal ---
    lambda n, f, ts, h, p: (
        f"{n}  {ts}",
        f"续火  {f} 天",
        f"sig  {h}",
        f"latency  {p}",
    ),
    # --- 1: Architectural Blueprint ---
    lambda n, f, ts, h, p: (
        f"┌─ {n}",
        f"│  {ts}",
        f"│  streak: {f} days",
        f"│  hash: {h}",
        f"│  ping: {p}",
        "└─ ok",
    ),
    # --- 2: Receipt ---
    lambda n, f, ts, _h, p: (
        "─ DAILY STREAK ─",
        f"to  {n}",
        f"days  {f}",
        f"at  {ts}",
        f"net  {p}",
        "─ END ─",
    ),
    # --- 3: Index / Card ---
    lambda n, f, ts, h, p: (
        "─ log ─",
        f"user  {n}",
        f"sday  {f}d",
        f"time  {ts}",
        f"idat  {h}",
        f"ping  {p}",
    ),
    # --- 4: Timestamp Anchor ---
    lambda n, f, ts, h, _p: (
        f"⏱ {ts}",
        f"[{n}] streak={f}d",
        f"sig {h}",
    ),
]

WIDGETS = [
    lambda: random.choice([
        f"seed {random.randint(1000, 9999)}",
        f"#{random.getrandbits(8):02x}",
        f"v{random.randint(1, 9)}.{random.randint(0, 9)}.{random.randint(0, 9)}",
    ]),
    lambda: f"delay {random.randint(8, 45)}ms",
    lambda: "",
    lambda: random.choice(["—", "·", ""]),
]


def generate_message(name: str, fire: str) -> tuple[list[str], str]:
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    hex_id = binascii.hexlify(os.urandom(3)).decode().upper()
    ping_ms = f"{now.microsecond % 40 + 10}ms"

    body_lines = random.choice(TEMPLATES)(name, fire, timestamp, hex_id, ping_ms)
    message_lines = list(body_lines)

    n_widgets = random.randint(0, 2)
    for _ in range(n_widgets):
        widget = random.choice(WIDGETS)()
        if widget:
            message_lines.append(widget)

    return message_lines, timestamp
