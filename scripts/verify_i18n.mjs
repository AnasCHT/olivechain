// Headless check of the i18n engine: load i18n.js under a stubbed DOM,
// switch languages, and confirm OC.t() returns the right strings + RTL.
import fs from "node:fs";

const src = fs.readFileSync(new URL("../frontend/i18n.js", import.meta.url), "utf-8");

function run(lang) {
  const store = { oc_lang: lang };
  const heads = [];
  const html = { lang: "", dir: "", };
  const sandbox = {
    localStorage: {
      getItem: k => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = v; },
    },
    document: {
      documentElement: html,
      createElement: () => ({ style: {}, setAttribute() {}, set textContent(_) {}, }),
      getElementById: () => null,
      head: { appendChild: n => heads.push(n) },
    },
    window: {},
  };
  // execute the IIFE with our stubs in scope
  const fn = new Function("localStorage", "document", "window",
    src + "\n;return window.OC;");
  const OC = fn(sandbox.localStorage, sandbox.document, sandbox.window);
  return { OC, dir: html.dir, lang: html.lang };
}

const cases = [
  ["en", "c.verify", "Verify my bottle", "ltr"],
  ["fr", "c.verify", "Vérifier ma bouteille", "ltr"],
  ["ar", "c.verify", "تحقّق من زجاجتي", "rtl"],
  ["fr", "p.st.Milled", "Pressé", "ltr"],
  ["ar", "p.st.Milled", "عُصر", "rtl"],
  ["fr", "l.lhint", "Scannez pour voir tout l'historique signé de cette huile", "ltr"],
  ["ar", "l.lsub", "أصل ودائرية موثّقان", "rtl"],
  ["fr", "s.scans", null, "ltr"],  // interpolation checked below
];

let ok = true;
for (const [lang, key, expect, dir] of cases) {
  const { OC, dir: gotDir } = run(lang);
  const got = OC.t(key);
  const pass = (expect === null || got === expect) && gotDir === dir;
  if (!pass) ok = false;
  console.log(`${pass ? "ok  " : "FAIL"} ${lang} ${key} -> "${got}" [dir=${gotDir}]`);
}

// interpolation
const { OC } = run("fr");
const interp = OC.t("s.scans", { n: 7 });
const interpOk = interp === "7 scans consommateurs";
console.log(`${interpOk ? "ok  " : "FAIL"} fr interpolation -> "${interp}"`);
if (!interpOk) ok = false;

// missing-key fallback returns the key itself
const fallback = OC.t("nonexistent.key");
const fbOk = fallback === "nonexistent.key";
console.log(`${fbOk ? "ok  " : "FAIL"} missing-key fallback -> "${fallback}"`);
if (!fbOk) ok = false;

process.exit(ok ? 0 : 1);
