"""CDP 驱动的平台前端端到端验收脚本（无头 Edge）。

用法: .venv/Scripts/python tests/e2e_cdp.py
流程: 打开平台 -> 自动会诊全流程 -> MDT 全流程 -> 截图 -> 输出结果 JSON。
"""
import base64
import json
import time
import urllib.request

import websocket

BASE = "http://127.0.0.1:8765/"
CDP_HTTP = "http://127.0.0.1:9222"


def http_json(url, method="GET"):
    req = urllib.request.Request(url, method=method)
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=120, suppress_origin=True)
        self.mid = 0

    def send(self, method, **params):
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.mid:
                if "error" in msg:
                    raise RuntimeError(str(msg["error"]))
                return msg.get("result", {})

    def evaluate(self, expr, await_promise=True):
        r = self.send("Runtime.evaluate", expression=expr,
                      awaitPromise=await_promise, returnByValue=True)
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            raise RuntimeError("PAGE EXC: " + (d.get("exception", {}).get("description") or d.get("text", "")))
        return r.get("result", {}).get("value")

    def screenshot(self, path):
        r = self.send("Page.captureScreenshot", format="png")
        with open(path, "wb") as f:
            f.write(base64.b64decode(r["data"]))


def main():
    tab = http_json(CDP_HTTP + "/json/new?" + BASE.replace("/", "%2F"), "PUT")
    c = CDP(tab["webSocketDebuggerUrl"])
    c.send("Runtime.enable")
    c.send("Page.enable")
    time.sleep(2.5)

    result = {"errors": []}

    def js(expr):
        return c.evaluate(expr)

    # ---------- 页面加载检查 ----------
    result["load"] = js("""(() => ({
        modeBtns: document.querySelectorAll('.mode-btn').length,
        caseItems: document.querySelectorAll('.case-item').length,
        datasets: document.querySelectorAll('#datasetTabs button').length,
        splash: !!document.getElementById('splash'),
        appJsOk: typeof startConsultation === 'function',
        title: document.title,
    }))()""")

    # ---------- 穿过启动过渡页 ----------
    result["splash_click"] = js("""(() => {
        const card = document.querySelector('.splash-card[data-mode="mdt"]');
        if (card) { card.click(); return 'clicked'; }
        return 'no-splash';
    })()""")
    time.sleep(0.8)

    # ---------- 自动会诊全流程 ----------
    js("""window.__errs = [];
          window.addEventListener('error', e => __errs.push(e.message + ' @' + e.lineno));
          window.addEventListener('unhandledrejection', e => __errs.push('REJ: ' + (e.reason?.message || e.reason)));""")
    js("""(() => { document.querySelector('.case-item').click(); })()""")
    js("""(() => { document.querySelector('.starter[data-act="auto"]') ||
                    document.getElementById('btnStart'); })()""")
    # 直接走与用户等价的路径: 选模式 -> 点开始按钮
    js("""(async () => {
        document.querySelectorAll('.mode-btn')[2].click();
        document.getElementById('btnStart').click();
    })()""")
    time.sleep(10)
    result["auto"] = js("""(() => ({
        bubbles: document.querySelectorAll('.msg').length,
        notes: document.querySelectorAll('.system-note').length,
        verdict: document.querySelectorAll('.verdict-card').length,
        progress: document.getElementById('progress')?.textContent || '',
        verdictText: (document.querySelector('.verdict-card')?.innerText || '').slice(0, 120),
    }))()""")

    # ---------- MDT 全流程（含预问诊追问） ----------
    js("""(async () => {
        document.getElementById('btnReset').click();                // 清掉上一场
        document.querySelectorAll('.mode-btn')[0].click();          // 会诊工作台
        document.getElementById('tipFillCase').click();             // 从病例库填入
        document.getElementById('btnStart').click();                // 第一次提交 -> 触发追问
    })()""")
    time.sleep(3)
    result["clarify"] = js("""(() => ({
        assistant: document.querySelectorAll('.msg.summary').length,
        btnText: document.getElementById('btnStart').textContent,
    }))()""")
    js("""(async () => {
        document.getElementById('humanInput').value = '症状持续 3 天；无发热；既往体健，无药物过敏，未用药。';
        document.getElementById('btnStart').click();                // 回答追问 -> 正式会诊
    })()""")
    time.sleep(8)
    result["mdt"] = js("""(() => ({
        specialists: document.querySelectorAll('.msg.specialist').length,
        summaries: document.querySelectorAll('.msg.summary').length,
        report: document.querySelectorAll('.report-card').length,
        reportText: (document.querySelector('.report-card')?.innerText || '').slice(0, 150),
    }))()""")

    # ---------- 设置弹窗 ----------
    js("""(() => { document.getElementById('btnSettings').click(); })()""")
    time.sleep(0.5)
    result["settings"] = js("""(() => ({
        modalVisible: !document.getElementById('settingsModal').classList.contains('hidden'),
        specBoxes: document.querySelectorAll('#specBoxes input').length,
        roleModelInputs: ['doctorModel','patientModel','measurementModel','moderatorModel']
            .filter(id => document.getElementById(id)).length,
    }))()""")
    js("""(() => { document.getElementById('btnCloseSettings').click(); })()""")

    result["jsErrors"] = js("window.__errs || []")
    result["pageErrors"] = result.pop("errors")

    # ---------- 截图 ----------
    shot = c.send("Page.captureScreenshot", format="png")
    with open("e2e_final.png", "wb") as f:
        f.write(base64.b64decode(shot["data"]))

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
