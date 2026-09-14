#!/usr/bin/env python3
"""
CSDN 博客文章链接采集器
用法:
  python3 csdn_blog_link_grab.py <CSDN账号ID> [--output DIR]

示例:
  python3 csdn_blog_link_grab.py 2501_92808422
  python3 csdn_blog_link_grab.py 2501_93367079 --output /path/to/output

功能:
  通过 Edge CDP 驱动，访问 CSDN 账号的 /article/list/N 分页列表，
  逐页提取每篇文章的标题和链接，保存为 JSON 和 TXT 文件。

要求:
  - Edge 浏览器已开启远程调试端口 (localhost:9222)
  - 已安装 websockets 库 (pip install websockets)
  - 已登录 CSDN（标签页需在 csdn.net 域下）
"""
import asyncio
import json
import sys
import time
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"


def parse_args() -> tuple:
    """解析命令行参数，返回 (account_id, output_dir)"""
    args = sys.argv[1:]
    account_id = None
    output_dir = OUTPUT_DIR

    i = 0
    while i < len(args):
        if args[i] == "--output" and i + 1 < len(args):
            output_dir = Path(args[i + 1])
            i += 2
        elif not args[i].startswith("--"):
            account_id = args[i]
            i += 1
        else:
            i += 1

    if not account_id:
        print("用法: python3 csdn_blog_link_grab.py <CSDN账号ID> [--output DIR]")
        print("示例: python3 csdn_blog_link_grab.py 2501_92808422")
        sys.exit(1)

    return account_id, output_dir


async def main():
    account_id, output_dir = parse_args()
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 连接 CDP ──────────────────────────────────────────────
    resp = urllib.request.urlopen("http://localhost:9222/json", timeout=5)
    tabs = json.loads(resp.read())

    tab = None
    for t in tabs:
        if "csdn.net" in t.get("url", "") and t.get("webSocketDebuggerUrl"):
            tab = t
            break

    if not tab:
        print("未找到 csdn.net 标签页。请先在 Edge 中打开任意 CSDN 页面。")
        sys.exit(1)

    import websockets

    ws_url = tab["webSocketDebuggerUrl"]
    async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:
        # ── CDP 辅助函数 ──────────────────────────────────────
        async def cmd(method, params=None):
            mid = int(time.time() * 1000) % 100000
            await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                r = json.loads(await ws.recv())
                if r.get("id") == mid:
                    return r.get("result", {})

        async def js(expr):
            r = await cmd("Runtime.evaluate", {
                "expression": expr,
                "returnByValue": True,
                "awaitPromise": True,
            })
            v = r.get("result", {})
            if v.get("type") != "undefined" and "value" in v:
                val = v["value"]
                return str(val) if not isinstance(val, str) else val
            return ""

        await cmd("Page.enable")

        # ── 提取函数 ──────────────────────────────────────────
        async def extract_page():
            """提取当前页面中该账号的所有文章"""
            code = r"""
            (function(){
                var r=[],s={};
                document.querySelectorAll('a').forEach(function(a){
                    var h=a.href||'', m=h.match(/\/article\/details\/(\d+)/);
                    if(m&&m[1]&&!s[m[1]]){
                        s[m[1]]=1;
                        var t=(a.innerText||a.title||'').trim().split('\n')[0].trim();
                        if(h.indexOf(ACCOUNT_ID)>=0&&t.length>3)
                            r.push({id:m[1],title:t,url:'https://blog.csdn.net/'+ACCOUNT_ID+'/article/details/'+m[1]});
                    }
                });
                return JSON.stringify(r);
            })()
            """.replace("ACCOUNT_ID", f'"{account_id}"')
            result = await js(code)
            if result and result != "[]":
                return json.loads(result)
            return []

        # ── 逐页翻取 ──────────────────────────────────────────
        all_articles = []
        seen_ids = set()
        blog_url = f"https://blog.csdn.net/{account_id}"

        print(f"开始抓取: {blog_url}")
        print(f"输出目录: {output_dir}")

        for page in range(1, 50):
            # 导航到中间页强制刷新 SPA
            if page == 1:
                await cmd("Page.navigate", {"url": f"{blog_url}/article/list/1"})
            else:
                await cmd("Page.navigate", {"url": "about:blank"})
                for _ in range(5):
                    await asyncio.sleep(0.5)
                    if await js("document.readyState") == "complete":
                        break
                await cmd("Page.navigate", {"url": f"{blog_url}/article/list/{page}"})

            # 等待加载
            for i in range(30):
                await asyncio.sleep(1)
                if await js("document.readyState") == "complete":
                    break

            await asyncio.sleep(3)
            await js("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)

            articles = await extract_page()
            new_count = 0
            for a in articles:
                if a["id"] not in seen_ids:
                    seen_ids.add(a["id"])
                    all_articles.append(a)
                    new_count += 1

            if new_count > 0:
                print(f"  第 {page} 页: +{new_count} 篇 (累计 {len(all_articles)} 篇)")
            else:
                print(f"  第 {page} 页: 无新增，结束翻页")
                break

            await asyncio.sleep(1)

        # ── 保存 ──────────────────────────────────────────────
        json_path = output_dir / f"csdn_{account_id}_links.json"
        txt_path = output_dir / f"csdn_{account_id}_links.txt"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(all_articles, f, ensure_ascii=False, indent=2)

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"CSDN账号: {account_id}\n")
            f.write(f"主页: {blog_url}\n")
            f.write(f"共 {len(all_articles)} 篇文章\n")
            f.write("=" * 60 + "\n\n")
            for i, a in enumerate(all_articles, 1):
                f.write(f"{i:4d}. {a['title']}\n")
                f.write(f"      {a['url']}\n\n")

        print(f"\n完成！共 {len(all_articles)} 篇文章")
        print(f"   JSON: {json_path}")
        print(f"   TXT:  {txt_path}")


if __name__ == "__main__":
    asyncio.run(main())
