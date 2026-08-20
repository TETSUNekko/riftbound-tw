# -*- coding: utf-8 -*-
"""符文戰場台灣賽事查詢 — tkinter 介面版。

抓一次資料放記憶體，之後所有篩選都是即時的（不用再按搜尋）。
"""
import datetime, json, os, queue, threading, tkinter as tk, webbrowser
from tkinter import ttk, messagebox

import lol_tw_events as core

STATUS_CHOICES = [("全部", None), ("報名中", 2), ("即將開始", 1), ("進行中", 3), ("已結束", 4)]
TYPE_CHOICES = [("全部", None), ("符文競技 Regular Play", "regular_play"),
                ("符文之夜 Nexus Night", "nexus_night"),
                ("召喚師激鬥戰 Summoner Skirmish", "summoner_skirmish"),
                ("巡迴資格賽 Regional Qualifier", "regional_qualifier")]
FEE_CHOICES = [("全部", None), ("免費", 0), ("<=100", 100), ("<=200", 200), ("<=300", 300),
               ("<=500", 500)]
PEOPLE_CHOICES = [("全部", None), (">=8 人", 8), (">=16 人", 16), (">=32 人", 32), (">=64 人", 64)]
DAY_CHOICES = [("全部", None), ("1 天內", 1), ("3 天內", 3), ("7 天內", 7), ("30 天內", 30)]
DIST_CHOICES = [("全部", None), ("5 km 內", 5), ("10 km 內", 10), ("20 km 內", 20), ("50 km 內", 50)]

COLS = [("dist", "距離(km)", 80), ("date", "日期", 90), ("status", "狀態", 70),
        ("type", "類型", 100), ("name", "活動名稱", 200), ("shop", "店家", 130),
        ("fee", "報名費", 70), ("people", "人數上限", 75), ("mode", "賽制", 130),
        ("addr", "地址", 240), ("apply", "報名期間", 170)]
MODES = {"swiss_bo1": "瑞士制 BO1", "swiss_bo3": "瑞士制 BO3",
         "single_bo1": "淘汰制 BO1", "single_bo3": "淘汰制 BO3"}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("符文戰場 台灣賽事查詢")
        self.geometry("1380x680")
        self.msgq = queue.Queue()
        self.events = []      # 已抓取（含距離）的全部活動
        self.rows = {}
        self.sort_state = {}

        top = ttk.Frame(self, padding=(8, 8, 8, 2))
        top.pack(fill="x")
        ttk.Label(top, text="你的地址：").pack(side="left")
        self.addr = ttk.Entry(top, width=38)
        self.addr.pack(side="left", padx=4)
        self.addr.insert(0, self._load(".lastaddr.json", ""))
        self.addr.bind("<Return>", lambda e: self.reload())
        self.btn = ttk.Button(top, text="抓取 / 更新資料", command=self.reload)
        self.btn.pack(side="left", padx=8)
        ttk.Label(top, text="關鍵字：").pack(side="left", padx=(12, 0))
        self.kw = ttk.Entry(top, width=20)
        self.kw.pack(side="left", padx=4)
        self.kw.bind("<KeyRelease>", lambda e: self.apply_filters())

        fil = ttk.Frame(self, padding=(8, 2, 8, 6))
        fil.pack(fill="x")
        self.status = self._combo(fil, "活動狀態", STATUS_CHOICES, 10)
        self.atype = self._combo(fil, "活動類型", TYPE_CHOICES, 24)
        self.fee = self._combo(fil, "報名費", FEE_CHOICES, 8)
        self.people = self._combo(fil, "人數", PEOPLE_CHOICES, 8)
        self.day = self._combo(fil, "舉辦時間", DAY_CHOICES, 8)
        self.dist = self._combo(fil, "距離", DIST_CHOICES, 9)

        self.tree = ttk.Treeview(self, columns=[c[0] for c in COLS], show="headings")
        for key, text, width in COLS:
            self.tree.heading(key, text=text, command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=width, anchor="w")
        vs = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        vs.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True, padx=8)
        self.tree.bind("<Double-1>", self.open_detail)

        self.info = ttk.Label(self, text="讀取中…（雙擊列可開啟活動頁）", padding=6)
        self.info.pack(fill="x")
        self.after(100, self.drain)
        self.after(300, self.reload)

    def _combo(self, parent, label, choices, width):
        ttk.Label(parent, text=label + "：").pack(side="left", padx=(8, 0))
        cb = ttk.Combobox(parent, width=width, state="readonly", values=[c[0] for c in choices])
        cb.current(0)
        cb.choices = dict(choices)
        cb.pack(side="left", padx=2)
        cb.bind("<<ComboboxSelected>>", lambda e: self.apply_filters())
        return cb

    # ponytail: 兩個小 json 存偏好就夠，不需要設定系統
    def _load(self, name, fallback):
        try:
            return json.load(open(os.path.join(core.BASE_DIR, name), encoding="utf8"))
        except Exception:
            return fallback

    def _save(self, name, value):
        # ponytail: 放在唯讀資料夾（如 Program Files）就靜靜跳過，不值得為此中斷查詢
        try:
            json.dump(value, open(os.path.join(core.BASE_DIR, name), "w", encoding="utf8"),
                      ensure_ascii=False)
        except OSError:
            pass

    # ---------- 抓資料（慢，開執行緒） ----------
    def reload(self):
        self.btn.state(["disabled"])
        addr = self.addr.get().strip()
        if addr:
            self._save(".lastaddr.json", addr)
        threading.Thread(target=self.work, args=(addr,), daemon=True).start()

    def work(self, addr):
        try:
            self.msgq.put(("info", "抓取活動列表…"))
            events = core.fetch_tw()
            cache = json.load(open(core.CACHE, encoding="utf8")) if os.path.exists(core.CACHE) else {}
            if addr:
                me = core.geocode(addr, cache)
                if not me:
                    raise ValueError("無法定位地址：" + addr)
                for i, e in enumerate(events, 1):
                    pos = core.geocode(e["address"], cache)
                    e["distance_km"] = round(core.haversine(me, pos), 2) if pos else None
                    self.msgq.put(("info", "計算距離 %d/%d（首次較慢，之後有快取）" % (i, len(events))))
                    self._save(os.path.basename(core.CACHE), cache)
            self.msgq.put(("done", events))
        except Exception as ex:
            self.msgq.put(("error", str(ex)))

    def drain(self):
        while not self.msgq.empty():
            kind, payload = self.msgq.get()
            if kind == "info":
                self.info.config(text=payload)
            elif kind == "error":
                self.btn.state(["!disabled"])
                self.info.config(text="失敗")
                messagebox.showerror("錯誤", payload)
            else:
                self.events = payload
                self.btn.state(["!disabled"])
                self.apply_filters()
        self.after(100, self.drain)

    # ---------- 篩選（純記憶體，改條件即時更新） ----------
    def apply_filters(self):
        status = self.status.choices[self.status.get()]
        atype = self.atype.choices[self.atype.get()]
        fee = self.fee.choices[self.fee.get()]
        people = self.people.choices[self.people.get()]
        day = self.day.choices[self.day.get()]
        dist = self.dist.choices[self.dist.get()]
        kw = self.kw.get().strip()
        today = datetime.date.today()

        def keep(e):
            if status and e["activityStatus"] != status:
                return False
            if atype and e["activityType"] != atype:
                return False
            if fee is not None and float(e["applyAmount"]) > fee:
                return False
            if people and (e["maxUser"] or 0) < people:
                return False
            if day:
                try:
                    gap = (datetime.date.fromisoformat(e["startTime"]) - today).days
                except ValueError:
                    return False
                if gap < 0 or gap > day:
                    return False
            if dist is not None and (e.get("distance_km") is None or e["distance_km"] > dist):
                return False
            if kw and kw not in (e["name"] + e["shopName"] + e["address"]):
                return False
            return True

        rows = [e for e in self.events if keep(e)]
        rows.sort(key=lambda e: (e.get("distance_km") is None, e.get("distance_km") or 0,
                                 e["startTime"]))
        self.fill(rows)

    def fill(self, events):
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        for e in events:
            d = e.get("distance_km")
            iid = self.tree.insert("", "end", values=(
                "%.2f" % d if d is not None else "-", e["startTime"],
                core.STATUS.get(e["activityStatus"], "?"),
                core.TYPES.get(e["activityType"], e["activityType"]), e["name"], e["shopName"],
                "%g" % e["applyAmount"], e["maxUser"],
                MODES.get(e["battleMode"], e["battleMode"] or ""), e["address"],
                "%s ~ %s" % (e["applyStartTime"], e["applyEndTime"])))
            self.rows[iid] = e["id"]
        self.info.config(text="符合條件 %d / 全台 %d 筆（雙擊列開啟活動頁，點欄位標題可排序）"
                              % (len(events), len(self.events)))

    def sort_by(self, col):
        """點欄位標題切換升冪/降冪；數字欄按數值排。"""
        desc = not self.sort_state.get(col, False)
        self.sort_state = {col: desc}

        def key(iid):
            v = self.tree.set(iid, col)
            if v == "-":
                return (float("inf"), "")          # 距離未知的排最後
            try:
                return (float(v), "")
            except ValueError:
                return (0.0, v)

        for i, iid in enumerate(sorted(self.tree.get_children(""), key=key, reverse=desc)):
            self.tree.move(iid, "", i)
        for k, text, _w in COLS:
            self.tree.heading(k, text=text + (" ▼" if desc else " ▲") if k == col else text)

    def open_detail(self, _):
        sel = self.tree.focus()
        if sel in self.rows:
            webbrowser.open("https://tc.playloltcg.com/activity-detail.html?id=%s" % self.rows[sel])


if __name__ == "__main__":
    App().mainloop()
