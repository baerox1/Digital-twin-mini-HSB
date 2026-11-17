"""AP 1: Enter-/In-Sensoren eines Blocks aus einem Rocrail-Log und Δt.

Der Mitschnitt ist ein Strom aus <xmlh><xml size="N"/></xmlh> plus genau N Bytes
Nutzlast. Zeitstempel stehen nur im Dateinamen (reiner Ziffernstamm) und in
den clock-Nachrichten; dazwischen wird über die Nachrichtenreihenfolge
interpoliert. Δt innerhalb einer Minute ist damit eine Näherung.

Enter ist die letzte steigende fb-Flanke vor bk.entering false→true, In die
letzte steigende Flanke danach und vor true→false. Welche Lok den Block
befährt und mit welchem V_cmd, kommt aus der letzten fachlichen lc-Meldung.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

XMLH = re.compile(br"<xmlh>\s*<xml\s+size=\"(\d+)\"\s*/>\s*</xmlh>", re.S)
LOCO_FIELDS = ("V", "mode", "modereason", "blockid", "destblockid")

ROOT = Path(__file__).resolve().parent
DEFAULT_LOG = ROOT.parent / "1771731551.log"


def _payload(data: bytes, start: int, size: int) -> bytes:
    """N Bytes ab start. Logs mit LF statt CRLF sind ein Byte kürzer als size."""
    exact = data[start : start + size]
    try:
        ET.fromstring(exact)
        return exact
    except ET.ParseError:
        return data[start : start + size - 1]


def parse_stream(path: Path) -> list[dict]:
    """Liest den Byte-Strom und liefert eine Nachricht pro xmlh-Frame."""
    data = path.read_bytes()
    messages: list[dict] = []
    errors: list[str] = []
    for match in XMLH.finditer(data):
        size = int(match.group(1))
        payload = _payload(data, match.end(), size)
        try:
            element = ET.fromstring(payload)
        except ET.ParseError as exc:
            errors.append(f"seq {len(messages)}: {exc}")
            continue
        messages.append(
            {
                "seq": len(messages),
                "tag": element.tag,
                "attrib": dict(element.attrib),
            }
        )
    if errors:
        print(f"{len(errors)} Nachrichten nicht gelesen, z. B.: {errors[0]}")
    if not messages:
        raise ValueError(f"Keine Rocrail-Nachrichten in {path}")
    return messages


def assign_timestamps(messages: list[dict], path: Path) -> None:
    """Zeitanker aus Dateiname und clock, linear interpoliert wie im Labor-Notebook."""
    anchors: list[tuple[int, float]] = []
    if path.stem.isdigit():
        anchors.append((0, float(path.stem)))
    for message in messages:
        if message["tag"] != "clock":
            continue
        raw = message["attrib"].get("time")
        if raw is None or not str(raw).lstrip("-").isdigit():
            continue
        anchors.append((message["seq"], float(raw)))
    anchors = sorted(set(anchors))
    if len(anchors) < 2:
        raise ValueError("Zu wenige Zeitanker (Dateiname/clock) für eine Interpolation.")
    times = [anchor[1] for anchor in anchors]
    if any(later < earlier for earlier, later in zip(times, times[1:])):
        print("Warnung: Zeitanker sind nicht monoton steigend.")

    for message in messages:
        message["epoch"] = _interpolate(message["seq"], anchors)


def _interpolate(seq: int, anchors: list[tuple[int, float]]) -> float:
    if seq <= anchors[0][0]:
        left, right = anchors[0], anchors[1]
    elif seq >= anchors[-1][0]:
        left, right = anchors[-2], anchors[-1]
    else:
        left, right = anchors[0], anchors[1]
        for earlier, later in zip(anchors, anchors[1:]):
            if earlier[0] <= seq <= later[0]:
                left, right = earlier, later
                break
    span = right[0] - left[0]
    rate = 0.0 if span == 0 else (right[1] - left[1]) / span
    return left[1] + (seq - left[0]) * rate


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def _speed(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def extract_passages(messages: list[dict]) -> list[dict]:
    """Paart Enter- und In-Flanke je Block und berechnet Δt in Sekunden."""
    locos: dict[str, dict[str, str]] = {}
    entering: dict[str, bool] = {}
    last_rise: dict | None = None
    open_runs: dict[str, dict] = {}
    passages: list[dict] = []

    for message in messages:
        tag = message["tag"]
        attrib = message["attrib"]

        if tag == "lc":
            _note_loco(locos, attrib)
            continue

        if tag == "fb" and attrib.get("state") == "true" and attrib.get("id"):
            last_rise = {
                "id": attrib["id"],
                "seq": message["seq"],
                "epoch": message["epoch"],
            }
            continue

        if tag != "bk" or "entering" not in attrib or "id" not in attrib:
            continue

        block = attrib["id"]
        now = attrib["entering"] == "true"
        before = entering.get(block)
        entering[block] = now
        loco_id = attrib.get("locid") or ""

        if before is not True and now and last_rise is not None:
            state = locos.get(loco_id, {})
            open_runs[block] = {
                "loco": loco_id,
                "from_block": state.get("blockid") or "",
                "block": block,
                "v_cmd": _speed(state.get("V")),
                "enter_sensor": last_rise["id"],
                "enter_seq": last_rise["seq"],
                "t_enter": last_rise["epoch"],
            }
            continue

        run = open_runs.get(block)
        if before is True and not now and run is not None and run["loco"] == loco_id:
            open_runs.pop(block, None)
            if last_rise is None or last_rise["seq"] <= run["enter_seq"]:
                continue
            if last_rise["id"] == run["enter_sensor"]:
                continue
            delta = last_rise["epoch"] - run["t_enter"]
            if delta < 0:
                continue
            origin = run["from_block"]
            passages.append(
                {
                    "loco": run["loco"],
                    "edge": f"{origin}->{block}" if origin else block,
                    "from_block": origin,
                    "block": block,
                    "v_cmd": run["v_cmd"],
                    "enter_sensor": run["enter_sensor"],
                    "in_sensor": last_rise["id"],
                    "t_enter": _iso(run["t_enter"]),
                    "t_in": _iso(last_rise["epoch"]),
                    "delta_t_s": round(delta, 6),
                }
            )

    passages.sort(key=lambda row: row["t_enter"])
    return passages


def _note_loco(locos: dict[str, dict[str, str]], attrib: dict) -> None:
    loco_id = attrib.get("id")
    if not loco_id:
        return
    state = locos.setdefault(loco_id, {})
    if state and all(state.get(key) == attrib.get(key, state.get(key)) for key in LOCO_FIELDS):
        return
    for key in LOCO_FIELDS:
        if key in attrib:
            state[key] = attrib[key]


def aggregate(passages: list[dict]) -> list[dict]:
    """Mittelwert und Stichproben-σ pro Lok, Kante und V_cmd, ab zwei Fahrten."""
    groups: dict[tuple, list[float]] = defaultdict(list)
    for row in passages:
        key = (row["loco"], row["edge"], row["v_cmd"])
        groups[key].append(row["delta_t_s"])

    profiles = []
    ordered = sorted(
        groups.items(),
        key=lambda item: (str(item[0][0]), str(item[0][1]), item[0][2] if item[0][2] is not None else -1),
    )
    for (loco, edge, v_cmd), samples in ordered:
        if len(samples) < 2:
            continue
        profiles.append(
            {
                "loco": loco,
                "edge": edge,
                "v_cmd": v_cmd,
                "n": len(samples),
                "delta_t_mean_s": round(statistics.fmean(samples), 6),
                "sigma_s": round(statistics.stdev(samples), 6),
            }
        )
    return profiles


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run(log_path: Path) -> tuple[list[dict], list[dict]]:
    messages = parse_stream(log_path)
    assign_timestamps(messages, log_path)
    passages = extract_passages(messages)
    profiles = aggregate(passages)
    write_json(
        ROOT / "edge_passages.json",
        {"source": str(log_path), "passages": passages},
    )
    write_json(
        ROOT / "edge_timings.json",
        {"source": str(log_path), "profiles": profiles},
    )
    print(f"{len(messages)} Nachrichten, {len(passages)} Durchfahrten, {len(profiles)} Profile mit n>=2")
    return passages, profiles


def main() -> None:
    parser = argparse.ArgumentParser(description="Enter/In-Δt aus einem Rocrail-Log (AP 1).")
    parser.add_argument("log", nargs="?", type=Path, default=DEFAULT_LOG, help="Pfad zur .log-Datei")
    args = parser.parse_args()
    log_path = args.log if args.log.is_absolute() else Path.cwd() / args.log
    if not log_path.is_file():
        raise SystemExit(f"Log nicht gefunden: {log_path}")
    passages, _profiles = run(log_path)
    for row in passages:
        if row["loco"] == "Captrain Vectron" and row["block"] == "west_cw_1":
            print(
                f"Captrain west_cw_1: {row['enter_sensor']} -> {row['in_sensor']}, "
                f"dt={row['delta_t_s']} s, Kante {row['edge']}, V={row['v_cmd']}"
            )
            break
    else:
        print("Keine Captrain-Durchfahrt durch west_cw_1 gefunden.")


if __name__ == "__main__":
    main()
