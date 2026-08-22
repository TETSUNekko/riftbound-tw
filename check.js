// 發布前的最小檢查：語法 + 每個被呼叫的函式都真的有定義 + 內建快照還在
// 用法：node check.js
const fs = require("fs");

const html = fs.readFileSync("index.html", "utf8");
const js = html.split("<script>")[1].split("</script>")[0];

// 1. 語法
new Function(js);

// 2. 呼叫的自訂函式是否都有定義（曾經因為改檔案時誤刪 buildFilters 而整頁掛掉）
const defined = new Set([...js.matchAll(/function\s+([A-Za-z_$][\w$]*)/g)].map(m => m[1]));
const declared = new Set([...js.matchAll(/([A-Za-z_$][\w$]*)\s*=[^=]/g)].map(m => m[1]));
const builtin = new Set(["if", "for", "while", "switch", "catch", "function", "return", "Number",
  "String", "Math", "Date", "JSON", "parseFloat", "parseInt", "fetch", "alert", "matchMedia",
  "isNaN", "encodeURIComponent", "Boolean", "Array", "Object"]);
const missing = [...new Set([...js.matchAll(/(?:^|[^.\w$])([a-z][\w$]*)\s*\(/g)].map(m => m[1]))]
  .filter(n => !defined.has(n) && !declared.has(n) && !builtin.has(n));
if (missing.length) throw new Error("呼叫了未定義的函式: " + missing.join(", "));

// 3. 快照與座標表還在
const pick = n => eval("(" + js.split(/\r?\n/).find(l => l.trim().startsWith("const " + n))
  .replace("const " + n + " = ", "").replace(/;\s*$/, "") + ")");
const snap = pick("SNAP"), venues = pick("VENUES");
if (!snap.list.length || !Object.keys(venues).length) throw new Error("快照或座標表是空的");

console.log(`ok — 快照 ${snap.list.length} 場（${snap.date}）、場地座標 ${Object.keys(venues).length} 筆`);
