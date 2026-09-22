// Drive the running KAMVEX window (WebView2 with --remote-debugging-port) for QA.
//
//   node ui.mjs shot <file.png>              full-page screenshot
//   node ui.mjs text                          visible text of the page (trimmed)
//   node ui.mjs eval "<js expression>"        evaluate in page, print JSON
//   node ui.mjs click "<button text>"         click the first button/anchor whose text includes it
//   node ui.mjs clicksel "<css selector>"     click by selector
//   node ui.mjs type "<css selector>" "<text>" [enter]
//   node ui.mjs nav <Conocimiento|Modelos|Comparar|Ajustes>
//   node ui.mjs wait "<text>" [timeoutMs]     wait until page text includes it
//   node ui.mjs console                       dump console messages captured during this command
//
// Launch the app first with WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9222

import puppeteer from "puppeteer-core";

const CDP = process.env.KAMVEX_CDP ?? "http://127.0.0.1:9222";
const [cmd, ...args] = process.argv.slice(2);

async function getPage(browser) {
  const pages = await browser.pages();
  const page = pages.find((p) => !p.url().startsWith("devtools://")) ?? pages[0];
  if (!page) throw new Error("no page found");
  return page;
}

function esc(s) {
  return s.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

async function clickByText(page, text) {
  const ok = await page.evaluate((t) => {
    const nodes = [...document.querySelectorAll("button, a, summary, [role=button]")];
    const el = nodes.find((n) => (n.innerText || n.textContent || "").trim().includes(t));
    if (!el) return false;
    el.scrollIntoView({ block: "center" });
    el.click();
    return true;
  }, text);
  if (!ok) throw new Error(`no clickable element with text: ${text}`);
}

async function main() {
  const browser = await puppeteer.connect({ browserURL: CDP, defaultViewport: null });
  const page = await getPage(browser);
  const logs = [];
  page.on("console", (m) => logs.push(`[${m.type()}] ${m.text()}`));
  page.on("pageerror", (e) => logs.push(`[pageerror] ${e.message}`));
  try {
    switch (cmd) {
      case "shot": {
        await page.screenshot({ path: args[0] ?? "shot.png", fullPage: false });
        console.log(`saved ${args[0] ?? "shot.png"}`);
        break;
      }
      case "text": {
        const t = await page.evaluate(() => document.body.innerText);
        console.log(t.replace(/\n{3,}/g, "\n\n").trim().slice(0, 6000));
        break;
      }
      case "eval": {
        const r = await page.evaluate(args[0]);
        console.log(JSON.stringify(r, null, 1));
        break;
      }
      case "click": {
        await clickByText(page, args[0]);
        await new Promise((r) => setTimeout(r, 400));
        console.log(`clicked ${args[0]}`);
        break;
      }
      case "clicksel": {
        await page.click(args[0]);
        await new Promise((r) => setTimeout(r, 400));
        console.log(`clicked ${args[0]}`);
        break;
      }
      case "type": {
        const [sel, text, enter] = args;
        await page.click(sel);
        await page.evaluate((s) => { const el = document.querySelector(s); if (el) el.value = ""; }, sel);
        await page.type(sel, text, { delay: 5 });
        if (enter === "enter") await page.keyboard.press("Enter");
        console.log(`typed into ${sel}`);
        break;
      }
      case "nav": {
        await clickByText(page, args[0]);
        await new Promise((r) => setTimeout(r, 500));
        console.log(`nav ${args[0]}`);
        break;
      }
      case "wait": {
        const [text, timeout = "60000"] = args;
        const deadline = Date.now() + Number(timeout);
        let found = false;
        while (Date.now() < deadline) {
          const t = await page.evaluate(() => document.body.innerText);
          if (t.includes(text)) { found = true; break; }
          await new Promise((r) => setTimeout(r, 500));
        }
        console.log(found ? `found: ${text}` : `TIMEOUT waiting for: ${text}`);
        if (!found) process.exitCode = 2;
        break;
      }
      case "console": {
        await new Promise((r) => setTimeout(r, Number(args[0] ?? 1500)));
        console.log(logs.join("\n") || "(no console output captured)");
        break;
      }
      default:
        console.log("unknown command");
        process.exitCode = 1;
    }
  } finally {
    browser.disconnect();
  }
}

main().catch((e) => {
  console.error("ERROR:", e.message);
  process.exit(1);
});
