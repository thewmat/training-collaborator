"""Minimal FIT decoder for Garmin activity files (standard library only).

decode(path) returns:
  records   [t, dist_m, kmh, hr, cad_spm, alt_m, power_w]  t = seconds from the first record (wall clock)
  laps      {t0, elapsed_s, timer_s, dist_m, kmh, hr, max_hr, cad, trigger}
  session   {start, dist_m, timer_s, elapsed_s, hr, max_hr, sport, sub_sport}
  pauses    [(t_stop, t_start)] timer stop/start pairs, seconds from the first record
  devices   [{source, device_type, manufacturer, product, serial}] from device_info (msg 23)
  hr_source "strap" | "wrist" | "none"  (see hr_source())
  vo2max, recovery_min  from Garmin's undocumented message 140 when present

Only the messages the analysis needs are decoded: file_id 0, session 18, lap 19, record 20,
event 21, device_info 23, and 140.
"""
import struct

FIT_EPOCH = 631065600   # 1989-12-31T00:00:00Z as a Unix timestamp

BASE = {0x00: "B", 0x01: "b", 0x02: "B", 0x83: "h", 0x84: "H", 0x85: "i", 0x86: "I", 0x07: "s",
        0x88: "f", 0x89: "d", 0x0A: "B", 0x8B: "H", 0x8C: "I", 0x0D: "B", 0x8E: "q", 0x8F: "Q", 0x90: "Q"}
INVALID = {"B": 0xFF, "b": 0x7F, "H": 0xFFFF, "h": 0x7FFF, "I": 0xFFFFFFFF, "i": 0x7FFFFFFF,
           "Q": 0xFFFFFFFFFFFFFFFF, "q": 0x7FFFFFFFFFFFFFFF}
WANT = {0, 18, 19, 20, 21, 23, 140}

# device_info.source_type: 0 ant, 1 antplus, 2 bluetooth, 3 bluetooth_low_energy, 4 wifi, 5 local
EXTERNAL_SOURCES = {0, 1, 2, 3}
ANTPLUS_HR = 120        # antplus_device_type.heart_rate
BLE_HR = 1              # ble_device_type.heart_rate
SPORTS_RUN = {1}        # sport.running


def messages(buf):
    """Yield (global_message_number, {field_number: value}) for the wanted messages."""
    hsize = buf[0]
    size = struct.unpack_from("<I", buf, 4)[0]
    pos, end, defs, last_ts = hsize, hsize + size, {}, 0
    while pos < end:
        h = buf[pos]; pos += 1
        if h & 0x80:                                    # compressed timestamp header
            local, off = (h >> 5) & 3, h & 0x1F
            ts = (last_ts & ~0x1F) + off
            if off < (last_ts & 0x1F):
                ts += 0x20
            last_ts = ts
        else:
            local, ts = h & 0x0F, None
            if h & 0x40:                                # definition message
                arch = buf[pos + 1]; e = ">" if arch else "<"
                gnum, nf = struct.unpack_from(e + "HB", buf, pos + 2); pos += 5
                fields = [tuple(buf[pos + 3 * i: pos + 3 * i + 3]) for i in range(nf)]; pos += 3 * nf
                devsize = 0
                if h & 0x20:
                    nd = buf[pos]; pos += 1
                    devsize = sum(buf[pos + 3 * i + 1] for i in range(nd)); pos += 3 * nd
                defs[local] = (e, gnum, fields, devsize)
                continue
        if local not in defs:
            break                                       # corrupt file: stop rather than misread
        e, gnum, fields, devsize = defs[local]
        rec = {}
        for num, sz, bt in fields:
            raw = buf[pos: pos + sz]; pos += sz
            if gnum not in WANT:
                continue
            c = BASE.get(bt, "B")
            if c == "s":
                continue
            w = struct.calcsize(c)
            if sz < w or sz % w:
                continue
            vals = struct.unpack(e + c * (sz // w), raw)
            v = vals[0] if len(vals) == 1 else vals
            if c in INVALID and len(vals) == 1 and (v == INVALID[c] or (bt in (0x0A, 0x8B, 0x8C, 0x90) and v == 0)):
                continue
            rec[num] = v
        pos += devsize
        if 253 in rec:
            last_ts = rec[253]
        elif ts is not None:
            rec[253] = ts
        if gnum in WANT:
            yield gnum, rec


def hr_source(devices, strap_products=()):
    """'strap' when an external heart-rate sensor (ANT+ or Bluetooth) is recorded, or a device whose
    product id is in strap_products; 'wrist' otherwise. Optical wrist HR under-reads in intervals
    and can lock onto cadence, so only strap HR is trusted for fitness reads."""
    for d in devices:
        if d.get("product") in strap_products and d.get("source") in EXTERNAL_SOURCES:
            return "strap"
        if d.get("source") in (0, 1) and d.get("device_type") == ANTPLUS_HR:
            return "strap"
        if d.get("source") in (2, 3) and d.get("device_type") == BLE_HR:
            return "strap"
    return "wrist"


def decode(path, strap_products=()):
    buf = open(path, "rb").read()
    laps, recs, sess, m140, devices, t0, file_id = [], [], {}, [], [], None, {}
    stopped, pauses = None, []
    for g, r in messages(buf):
        if g == 20:
            t = r.get(253)
            if t is None:
                continue
            t0 = t if t0 is None else t0
            spd = r.get(73, r.get(6))
            cad = r.get(4)
            alt = r.get(78, r.get(2))
            recs.append([t - t0, (r.get(5) or 0) / 100, round(spd / 1000 * 3.6, 2) if spd is not None else None,
                         r.get(3), cad * 2 if cad is not None else None,
                         round(alt / 5 - 500, 1) if isinstance(alt, int) else None, r.get(7)])
        elif g == 19:
            d = (r.get(9) or 0) / 100; tt = (r.get(8) or 0) / 1000
            spd = r.get(110, r.get(13))
            laps.append({"start": r.get(2), "elapsed_s": round((r.get(7) or 0) / 1000, 1), "timer_s": round(tt, 1),
                         "dist_m": round(d, 1),
                         "kmh": round(spd / 1000 * 3.6, 2) if spd else (round(d / tt * 3.6, 2) if tt else None),
                         "hr": r.get(15), "max_hr": r.get(16), "cad": r.get(17) * 2 if r.get(17) else None,
                         "power": r.get(19), "trigger": r.get(24)})
        elif g == 18:
            sess = {"start": r.get(2), "dist_m": (r.get(9) or 0) / 100, "timer_s": (r.get(8) or 0) / 1000,
                    "elapsed_s": (r.get(7) or 0) / 1000, "hr": r.get(16), "max_hr": r.get(17),
                    "sport": r.get(5), "sub_sport": r.get(6)}
        elif g == 21 and r.get(0) == 0 and 253 in r:     # event 0 = timer
            if r.get(1) in (1, 4) and stopped is None:      # stop / stop_all
                stopped = r[253]
            elif r.get(1) == 0 and stopped is not None:     # start
                pauses.append((stopped, r[253])); stopped = None
        elif g == 23:
            devices.append({"source": r.get(25), "device_type": r.get(1), "manufacturer": r.get(2),
                            "product": r.get(4), "serial": r.get(3)})
        elif g == 0:
            file_id = {"manufacturer": r.get(1), "product": r.get(2), "created": r.get(4)}
        elif g == 140:
            m140.append({str(k): v for k, v in r.items()})
    if t0 is not None:
        for l in laps:
            if l["start"] is not None:
                l["t0"] = l["start"] - t0
        pauses = [(a - t0, b - t0) for a, b in pauses]
    vo2 = rec_min = None
    for m in m140:
        if isinstance(m.get("7"), int):
            vo2 = round(m["7"] * 3.5 / 65536, 1)
        if isinstance(m.get("9"), int):
            rec_min = m["9"]
    uniq = {(d["source"], d["device_type"], d["product"], d["serial"]): d for d in devices}
    devices = list(uniq.values())
    src = hr_source(devices, strap_products) if any(r[3] for r in recs) else "none"
    return {"records": recs, "laps": laps, "session": sess, "pauses": pauses, "devices": devices,
            "file_id": file_id, "hr_source": src, "vo2max": vo2, "recovery_min": rec_min,
            "t0": t0}


def start_unix(d):
    """Unix timestamp of the first record (or session start)."""
    t = d.get("t0") or d["session"].get("start")
    return t + FIT_EPOCH if t is not None else None
