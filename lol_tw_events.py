# -*- coding: utf-8 -*-
"""符文戰場(Riftbound)台灣賽事爬蟲 + 依地址算最近場地。

用法:
    python lol_tw_events.py "台北市信義區市府路45號"
    python lol_tw_events.py "新竹市光復路二段101號" --top 20 --status 2
"""
import argparse, json, math, os, re, sys, time, urllib.parse, urllib.request

API = "https://lol-api.playloltcg.com/xcx/overseas/activity/list"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
# 打包成 exe 時 __file__ 在暫存目錄，快取要放在 exe 旁邊才留得住
BASE_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
CACHE = os.path.join(BASE_DIR, ".geocache.json")
UA = "lol-tcg-tw-events/1.0 (personal use)"

TYPES = {"regular_play": "符文競技", "nexus_night": "符文之夜",
         "summoner_skirmish": "召喚師激鬥戰", "regional_qualifier": "巡迴資格賽"}
STATUS = {1: "即將開始", 2: "報名中", 3: "進行中", 4: "已結束"}


def post(url, payload):
    req = urllib.request.Request(url, json.dumps(payload).encode(),
                                 {"Content-Type": "application/json", "User-Agent": UA})
    return json.load(urllib.request.urlopen(req, timeout=30))


def fetch_tw(status=None):
    """抓全部活動，只留 province == 台灣。"""
    out, page = [], 1
    while True:
        body = {"pageNum": page, "pageSize": 100}
        if status:
            body["activityStatus"] = status
        res = post(API, body)
        if res.get("code") != 0:
            raise SystemExit("API 錯誤: %s" % res.get("message"))
        lst = res["result"]["list"]
        out += [a for a in lst if a.get("province") == "台灣"
                and (not status or a.get("activityStatus") == status)]  # API 的 status 篩選不一定生效，這裡再濾一次
        if page * 100 >= res["result"]["total"] or not lst:
            return out
        page += 1


def _query(**kw):
    kw.update({"format": "json", "limit": 1, "countrycodes": "tw", "accept-language": "zh-TW"})
    url = NOMINATIM + "?" + urllib.parse.urlencode({k: v for k, v in kw.items() if v})
    try:
        r = json.load(urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30))
    except Exception:
        r = []
    time.sleep(1.1)          # Nominatim 使用條款：1 req/s
    return (float(r[0]["lat"]), float(r[0]["lon"])) if r else None


ADDR_RE = re.compile(r"^(?:\d{3,6})?\s*(?P<city>.{1,3}?[縣市])(?P<dist>.{1,4}?[區鄉鎮市])?(?P<rest>.*)$")
NUM = {"1": "一", "2": "二", "3": "三", "4": "四", "5": "五", "6": "六", "7": "七", "8": "八"}


def split_addr(addr):
    """台灣地址 -> (縣市, 行政區, 路名)。抓不到就整串當路名。"""
    m = ADDR_RE.match(addr.strip())
    if not m:
        return None, None, addr
    norm = lambda x: x.replace("台", "臺") if x else x
    street = re.sub(r"^.{1,5}?[村里]", "", m.group("rest"))
    street = re.sub(r"[巷弄號樓].*$", "", street)
    street = re.sub(r"[\d\-.之]+$", "", street).strip()
    street = re.sub(r"(\d)(?=段)", lambda g: NUM.get(g.group(1), g.group(1)), street)
    return norm(m.group("city")), norm(m.group("dist")), norm(street)


def geocode(addr, cache):
    """自由文字查詢，逐層退回：路 -> 行政區 -> 縣市。"""
    # ponytail: 只做到路名層級，門牌 OSM 台灣覆蓋率太低；要門牌精度就換 Google Geocoding API
    if addr in cache:
        return cache[addr]
    parts = [p for p in split_addr(addr) if p]
    tries = [" ".join(parts[:n]) for n in range(len(parts), 0, -1)] + [addr]
    hit = None
    for q in tries:
        hit = _query(q=q)
        if hit:
            break
    cache[addr] = hit
    return hit


def haversine(a, b):
    R = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("address", nargs="?", help="你現在的地址，省略則只列出活動")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--status", type=int, choices=[1, 2, 3, 4], help="1即將開始 2報名中 3進行中 4已結束")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    events = fetch_tw(args.status)
    cache = json.load(open(CACHE, encoding="utf8")) if os.path.exists(CACHE) else {}

    if args.address:
        me = geocode(args.address, cache)
        if not me:
            sys.exit("無法定位你的地址: " + args.address)
        for e in events:
            addr = e["address"]
            pos = geocode(addr, cache)
            e["distance_km"] = round(haversine(me, pos), 2) if pos else None
            json.dump(cache, open(CACHE, "w", encoding="utf8"), ensure_ascii=False)
        events.sort(key=lambda e: (e["distance_km"] is None, e["distance_km"] or 0))
        events = events[:args.top]

    if args.json:
        print(json.dumps(events, ensure_ascii=False, indent=2))
        return

    print("台灣活動 %d 筆%s\n" % (len(events), "（依距離排序）" if args.address else ""))
    for e in events:
        d = e.get("distance_km")
        print("%s | %s | %s" % (e["startTime"], TYPES.get(e["activityType"], e["activityType"]), e["name"]))
        print("  店家: %s  狀態: %s  報名費: %g  人數上限: %s"
              % (e["shopName"], STATUS.get(e["activityStatus"], "?"), e["applyAmount"], e["maxUser"]))
        print("  地址: %s%s" % (e["address"], "  (%.2f km)" % d if d is not None else ""))
        print("  報名期間: %s ~ %s" % (e["applyStartTime"], e["applyEndTime"]))
        print("  https://tc.playloltcg.com/activity-detail.html?id=%s\n" % e["id"])


def _selftest():
    assert abs(haversine((25.033, 121.565), (22.627, 120.302)) - 296) < 10
    assert split_addr("台南市中西區民生路一段89號") == ("臺南市", "中西區", "民生路一段")
    assert split_addr("台北市士林區大東路135號B1") == ("臺北市", "士林區", "大東路")
    assert split_addr("台北市南京東路二段95號B1")[2] == "南京東路二段"
    assert split_addr("台北市內湖區康寧路3段165巷14弄5號1樓") == ("臺北市", "內湖區", "康寧路三段")
    assert split_addr("新竹縣湖口鄉中正村溪南二街23號1樓") == ("新竹縣", "湖口鄉", "溪南二街")
    print("ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        main()
