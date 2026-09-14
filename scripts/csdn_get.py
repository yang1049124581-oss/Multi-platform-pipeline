#!/usr/bin/env python3
"""
CSDN Get — CSDN 账号文章全量采集 + 全文提取技能

用法:
  python3 csdn_get.py links    <账号ID>          扒取全部文章链接
  python3 csdn_get.py extract <links.json>       从链接清单扒全文
  python3 csdn_get.py full    <账号ID>           全流程: 扒链接→抽样→扒全文

示例:
  python3 csdn_get.py links 2501_92808422
  python3 csdn_get.py extract outputs/links_2501_92808422.json
  python3 csdn_get.py full 2501_92808422

输出:
  links  → outputs/csdn_{账号}_links.json + .txt
  extract → outputs/csdn_{账号}_articles.json (含 full_text)
  full    → 链接 + 抽样清单 + 文章全文

前置条件:
  - Edge 已开启远程调试端口 (--remote-debugging-port=9222)
  - 浏览器已有 csdn.net 标签页（已登录）
  - pip install websockets
"""
import asyncio
import json
import random
import re
import sys
import time
import urllib.request
from pathlib import Path

# ── 常量 ──
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
random.seed(42)


# ══════════════════════════════════════════════════════════════
#  CDP 通信
# ══════════════════════════════════════════════════════════════

async def connect_cdp():
    """连接 Edge CDP，返回一个可用标签页的 websocket"""
    resp = urllib.request.urlopen("http://localhost:9222/json", timeout=5)
    tabs = json.loads(resp.read())
    for t in tabs:
        if "csdn.net" in t.get("url", "") and t.get("webSocketDebuggerUrl"):
            return t
    print("❌ 未找到 csdn.net 标签页。请先在 Edge 中打开任意 CSDN 页面。")
    sys.exit(1)


async def cdp_session(ws_url):
    """返回 (cmd, jse) 两个异步函数"""
    import websockets
    ws = await websockets.connect(ws_url, max_size=10 * 1024 * 1024)

    async def cmd(method, params=None):
        mid = int(time.time() * 1000) % 100000
        await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            r = json.loads(await ws.recv())
            if r.get("id") == mid:
                return r.get("result", {})

    async def jse(expr):
        r = await cmd("Runtime.evaluate", {
            "expression": expr, "returnByValue": True, "awaitPromise": True,
        })
        v = r.get("result", {})
        if v.get("type") != "undefined" and "value" in v:
            val = v["value"]
            return str(val) if not isinstance(val, str) else val
        return ""

    return cmd, jse, ws


# ══════════════════════════════════════════════════════════════
#  模式1: 扒链接
# ══════════════════════════════════════════════════════════════

async def grab_links(account_id, output_dir):
    """通过 /article/list/N 分页获取全部文章链接"""
    tab = await connect_cdp()
    cmd, jse, ws = await cdp_session(tab["webSocketDebuggerUrl"])

    await cmd("Page.enable")
    all_articles, seen_ids = [], []
    blog_url = f"https://blog.csdn.net/{account_id}"

    print(f"[CSDN Get] 开始扒取链接: {blog_url}")

    for page in range(1, 50):
        # 导航（中间页强制刷新）
        if page == 1:
            await cmd("Page.navigate", {"url": f"{blog_url}/article/list/1"})
        else:
            await cmd("Page.navigate", {"url": "about:blank"})
            for _ in range(5):
                await asyncio.sleep(0.5)
                if await jse("document.readyState") == "complete":
                    break
            await cmd("Page.navigate", {"url": f"{blog_url}/article/list/{page}"})

        # 等待加载
        loaded = False
        for i in range(30):
            await asyncio.sleep(1)
            if await jse("document.readyState") == "complete":
                loaded = True
                break
        if not loaded:
            print(f"  ⚠ 第{page}页加载超时，终止翻页")
            break

        await asyncio.sleep(3)
        await jse("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)

        # 提取
        code = rf"""
        (function(){{
            var r=[],s={{}};
            document.querySelectorAll('a').forEach(function(a){{
                var h=a.href||'', m=h.match(/\/article\/details\/(\d+)/);
                if(m&&m[1]&&!s[m[1]]){{
                    s[m[1]]=1;
                    var t=(a.innerText||a.title||'').trim().split('\n')[0].trim();
                    if(h.indexOf('{account_id}')>=0&&t.length>3)
                        r.push({{id:m[1],title:t,url:'https://blog.csdn.net/{account_id}/article/details/'+m[1]}});
                }}
            }});
            return JSON.stringify(r);
        }})()
        """
        result = await jse(code)
        new_count = 0
        if result and result != "[]":
            for a in json.loads(result):
                if a["id"] not in seen_ids:
                    seen_ids.append(a["id"])
                    all_articles.append(a)
                    new_count += 1

        if new_count > 0:
            print(f"  第{page}页: +{new_count} (累计 {len(all_articles)})")
        else:
            print(f"  第{page}页: 无新增，翻页结束")
            break
        await asyncio.sleep(1)

    await ws.close()

    # 保存
    json_path = output_dir / f"csdn_{account_id}_links.json"
    txt_path = output_dir / f"csdn_{account_id}_links.txt"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"CSDN账号: {account_id}\n主页: {blog_url}\n共 {len(all_articles)} 篇文章\n{'='*60}\n\n")
        for i, a in enumerate(all_articles, 1):
            f.write(f"{i:4d}. {a['title']}\n      {a['url']}\n\n")

    print(f"\n✅ 完成！共 {len(all_articles)} 篇")
    print(f"   {json_path}")
    print(f"   {txt_path}")
    return all_articles


# ══════════════════════════════════════════════════════════════
#  模式2: 扒全文
# ══════════════════════════════════════════════════════════════

async def extract_articles(link_list, output_dir, label=""):
    """从链接清单提取全文结构化内容"""
    tab = await connect_cdp()
    cmd, jse, ws = await cdp_session(tab["webSocketDebuggerUrl"])
    await cmd("Page.enable")

    results = []
    total = len(link_list)
    errors = 0

    print(f"[CSDN Get] 开始提取全文: {total} 篇" + (f" ({label})" if label else ""))

    for idx, item in enumerate(link_list, 1):
        url = item if isinstance(item, str) else item.get("url", "")
        if not url or "csdn.net" not in url:
            results.append({
                "url": url, "title": "", "date": "", "full_text": "",
                "first_para": "", "headings": [], "cda_context": "",
                "cda_position_pct": -1, "word_count_est": 0, "_error": "非CSDN链接",
            })
            continue

        title_prefix = item.get("title", "")[:30] if isinstance(item, dict) else ""
        print(f"  [{idx}/{total}] {title_prefix}...", flush=True)

        try:
            await cmd("Page.navigate", {"url": url})
            loaded = False
            for i in range(25):
                await asyncio.sleep(0.5)
                if await jse("document.readyState") == "complete":
                    loaded = True
                    break
            if not loaded:
                raise TimeoutError("页面加载超时")
            await asyncio.sleep(1.5)

            code = r"""
            (function(){
                var r={};
                var titleEl = document.querySelector('h1.article-title, .title-article, h1');
                r.title = titleEl ? titleEl.innerText.trim() : '';

                var dateEl = document.querySelector('.article-info .date, .time, [class*="date"], [class*="time"]');
                r.date = dateEl ? dateEl.innerText.trim() : '';

                var contentEl = document.querySelector('#article_content, .article_content, .content, article');
                var fullText = contentEl ? contentEl.innerText : document.body.innerText;
                r.full_text = fullText.replace(/\s+/g, ' ').trim();
                r.first_para = fullText.substring(0, 300).replace(/\s+/g, ' ').trim();

                var headings = [];
                var headingMatches = fullText.match(/【[^】]+】/g);
                if (headingMatches) headings = headingMatches.map(function(h){return h.trim();});
                r.headings = headings;

                var cdaIdx = fullText.indexOf('CDA');
                if (cdaIdx >= 0) {
                    var before = fullText.substring(Math.max(0,cdaIdx-80), cdaIdx);
                    var after = fullText.substring(cdaIdx, Math.min(fullText.length,cdaIdx+120));
                    r.cda_context = (before + '【HERE】' + after).replace(/\s+/g, ' ').trim();
                    r.cda_position_pct = Math.round((cdaIdx / fullText.length) * 100);
                } else {
                    r.cda_context = ''; r.cda_position_pct = -1;
                }
                var cn = (fullText.match(/[\u4e00-\u9fff]/g) || []).length;
                var en = (fullText.match(/[a-zA-Z]+/g) || []).length;
                r.word_count_est = cn + en;
                r.url = window.location.href.split('?')[0];
                return JSON.stringify(r);
            })()
            """
            raw = await jse(code)
            if raw and raw != "{}":
                info = json.loads(raw)
            else:
                raise ValueError("提取结果为空")

            entry = {
                "url": url.split("?")[0],
                "title": info.get("title", ""),
                "date": info.get("date", ""),
                "full_text": info.get("full_text", ""),
                "first_para": info.get("first_para", ""),
                "headings": info.get("headings", []),
                "cda_context": info.get("cda_context", ""),
                "cda_position_pct": info.get("cda_position_pct", -1),
                "word_count_est": info.get("word_count_est", 0),
            }
            if isinstance(item, dict):
                for k in ("类别", "账号", "阶段"):
                    if k in item:
                        entry[k] = item[k]
            results.append(entry)

        except Exception as e:
            errors += 1
            print(f"    ⚠ 提取失败: {e}", flush=True)
            results.append({
                "url": url.split("?")[0], "title": "", "date": "",
                "full_text": "", "first_para": f"提取失败: {e}",
                "headings": [], "cda_context": "", "cda_position_pct": -1,
                "word_count_est": 0, "_error": str(e),
            })
            if isinstance(item, dict):
                for k in ("类别", "账号", "阶段"):
                    if k in item:
                        results[-1][k] = item[k]

    await ws.close()

    # 保存
    suffix = f"_{label}" if label else ""
    json_path = output_dir / f"csdn_articles{suffix}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    with_full = sum(1 for e in results if len(e.get("full_text", "")) > 100)
    print(f"\n✅ 完成！{len(results)} 篇 (含全文 {with_full}, 失败 {errors})")
    print(f"   {json_path}")
    return results


# ══════════════════════════════════════════════════════════════
#  模式3: 全流程 (扒链接→抽样→扒全文)
# ══════════════════════════════════════════════════════════════

async def full_pipeline(account_id, output_dir):
    """全流程: 扒链接 → 分层随机抽样 → 扒全文"""
    # 1. 扒链接
    all_links = await grab_links(account_id, output_dir)
    if not all_links:
        print("❌ 未获取到任何链接")
        return

    total = len(all_links)
    # 2. 分层随机抽样
    # 分成4阶段: 探索/转型/稳定/成熟
    stages = [
        (0, int(total * 0.15), 0.60, "探索期"),
        (int(total * 0.15), int(total * 0.35), 0.50, "转型期"),
        (int(total * 0.35), int(total * 0.70), 0.35, "稳定期"),
        (int(total * 0.70), total, 0.40, "成熟期"),
    ]
    manifest = []
    for s, e, rate, name in stages:
        pool = all_links[s:e]
        n = max(5, min(len(pool), int(len(pool) * rate)))
        sampled = random.sample(pool, n)
        for item in sampled:
            manifest.append({**item, "阶段": name})

    manifest_path = output_dir / f"sample_{account_id}.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"\n📋 抽样清单: {len(manifest)} 篇 → {manifest_path}")

    # 3. 扒全文
    articles = await extract_articles(manifest, output_dir, label=account_id)
    print(f"\n🎯 全流程完成! 账号 {account_id}: 共{total}篇, 抽样{len(manifest)}篇, 成功提取全文{sum(1 for a in articles if len(a.get('full_text',''))>100)}篇")


# ══════════════════════════════════════════════════════════════
#  CLI 入口
# ══════════════════════════════════════════════════════════════

def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)

    mode = args[0]
    target = args[1]
    output_dir = OUTPUT_DIR
    if "--output" in args:
        idx = args.index("--output")
        if idx + 1 < len(args):
            output_dir = Path(args[idx + 1])
    output_dir.mkdir(parents=True, exist_ok=True)

    if mode == "links":
        asyncio.run(grab_links(target, output_dir))
    elif mode == "extract":
        path = Path(target)
        if not path.exists():
            print(f"❌ 文件不存在: {path}")
            sys.exit(1)
        with open(path, "r", encoding="utf-8") as f:
            link_list = json.load(f)
        asyncio.run(extract_articles(link_list, output_dir))
    elif mode == "full":
        asyncio.run(full_pipeline(target, output_dir))
    else:
        print(f"❌ 未知模式: {mode}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
