#!/usr/bin/env python3
"""
CDP 驱动版多平台链接汇总工具
直接连接浏览器 CDP 端口，控制已有标签页导航并提取文章链接。
支持 Chrome (端口 9223) 和 Edge (端口 9222)，自动多端口扫描。
无需 opencli，无需浏览器扩展，全自动。
"""
import asyncio
import json
import re
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

# 浏览器路径（用于自启动提示）
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

PLATFORM_ORDER = ["公众号", "头条号", "百家号", "知乎", "CSDN"]
PLATFORM_LABELS = {
    "公众号": "公众号",
    "头条号": "头条号",
    "百家号": "百家号",
    "知乎": "知乎",
    "CSDN": "CSDN",
}

# 各平台配置
PLATFORMS = {
    "公众号": {
        "domain": "mp.weixin.qq.com",
        "nav_url": "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&lang=zh_CN&token={token}",
        "click": "发表记录",
        "parent_clicks": ["内容管理"],
        "fallback_url": "https://mp.weixin.qq.com/cgi-bin/appmsgpublish?sub=list&begin=0&count=10&token={token}&lang=zh_CN",
        "wait": 6,
        "click_wait": 4,
        "extract_js": """
(function(){
    var r=[],s={};
    document.querySelectorAll('a').forEach(function(a){
        var h=a.href||'';
        if(/mp\\.weixin\\.qq\\.com\\/s\\//.test(h)&&!s[h]){s[h]=1;r.push({title:(a.innerText||'').trim(),url:h});}
    });
    return JSON.stringify(r.slice(0,10));
})()
""",
    },
    "头条号": {
        "domain": "mp.toutiao.com",
        "nav_url": "https://mp.toutiao.com/profile_v4/manage/content/all",
        "click": None,
        "parent_clicks": [],
        "fallback_url": None,
        "wait": 18,   # 需要等待 Garfish 微前端加载渲染
        "click_wait": 0,
        "extract_js": """
(function(){
    var r=[],s={};
    document.querySelectorAll('a[href*=\"/item/\"]').forEach(function(a){
        var h=a.href||'';
        if(/toutiao\\.com\\/item\\//.test(h)&&!s[h]){s[h]=1;var t=(a.innerText||'').trim();if(t)r.push({title:t,url:h.split('?')[0]});}
    });
    return JSON.stringify(r.slice(0,10));
})()
""",
    },
    "百家号": {
        "domain": "baijiahao.baidu.com",
        "nav_url": "https://baijiahao.baidu.com/builder/rc/content/article",
        "click": "作品管理",
        "wait": 6,
        "click_wait": 5,
        "extract_js": """
(function(){
    var r=[],s={};
    document.querySelectorAll('a.cheetah-public').forEach(function(a){
        var h=a.href||'';var t=(a.innerText||'').trim();
        if(t&&!s[h]){s[h]=1;r.push({title:t,url:h});}
    });
    return JSON.stringify(r.slice(0,10));
})()
""",
    },
    "知乎": {
        "domain": "zhihu.com/creator",
        "nav_url": "https://www.zhihu.com/creator/manage/creation",
        "click": None,
        "wait": 6,
        "click_wait": 0,
        "extract_js": """
(function(){
    var r=[],s={};
    document.querySelectorAll('a').forEach(function(a){
        var h=a.href||'';
        if(h.indexOf('/edit')>-1)return;
        if(/zhuanlan\\.zhihu\\.com\\/p\\//.test(h)&&!s[h]){s[h]=1;
            var t=(a.innerText||'').trim();
            if(t){
                var l=t.split('\\n')[0];
                if(l.indexOf('文章')===0)l=l.substring(2);
                r.push({title:l.trim(),url:h.split('?')[0]});
            }
        }
    });
    return JSON.stringify(r.slice(0,10));
})()
""",
    },
    "CSDN": {
        "domain": "csdn.net",
        "nav_url": "https://mp.csdn.net/mp_blog/manage/article",
        "click": None,
        "wait": 6,
        "click_wait": 0,
        "extract_js": """
(function(){
    var a='2603_96020886';var r=[],s={};
    document.querySelectorAll('p.article-list-item-txt a').forEach(function(e){
        var h=e.getAttribute('href')||'';
        var m=h.match(/\\/editor\\/(\\d+)/);
        // 新格式: https://editor.csdn.net/md/?articleId=数字
        if(!m) m=h.match(/articleId=(\\d+)/);
        if(m){
            var u='https://blog.csdn.net/'+a+'/article/details/'+m[1];
            if(!s[u]){s[u]=1;r.push({title:e.innerText.trim(),url:u});}
        }
    });
    return JSON.stringify(r.slice(0,10));
})()
""",
    },
}


# ---------------------------------------------------------------------------
# CDP 底层通信
# ---------------------------------------------------------------------------
class CDP:
    def __init__(self):
        self.ws = None

    async def connect_to_tab(self, tab):
        import websockets
        ws_url = tab["webSocketDebuggerUrl"]
        self.ws = await websockets.connect(ws_url, max_size=10*1024*1024)

    async def cmd(self, method, params=None):
        if not self.ws:
            raise Exception("CDP not connected")
        msg_id = int(time.time() * 1000) % 100000
        await self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            r = json.loads(await self.ws.recv())
            if r.get("id") == msg_id:
                return r.get("result", {})

    async def eval(self, js: str) -> str:
        result = await self.cmd("Runtime.evaluate", {
            "expression": js,
            "returnByValue": True,
            "awaitPromise": True,
        })
        v = result.get("result", {})
        if v.get("type") != "undefined" and "value" in v:
            val = v["value"]
            return str(val) if not isinstance(val, str) else val
        return ""

    async def navigate(self, url: str):
        await self.cmd("Page.enable")
        await self.cmd("Page.navigate", {"url": url})
        # 等待加载完成
        for _ in range(30):
            await asyncio.sleep(1)
            r = await self.eval("document.readyState")
            if r == "complete":
                return

    async def click_text(self, text: str) -> bool:
        """点击包含指定文本的可见元素"""
        js = f"""
        (function(){{
            var all=document.querySelectorAll('a,span,div,li,button');
            for(var i=0;i<all.length;i++){{
                var el=all[i];
                if((el.innerText||'').trim()==='{text}'&&el.offsetParent!==null){{
                    el.click();
                    return true;
                }}
            }}
            return false;
        }})()
        """
        r = await self.eval(js)
        return r == "true"

    async def scroll_down(self):
        await self.eval("window.scrollTo(0, document.body.scrollHeight)")

    async def close(self):
        if self.ws:
            await self.ws.close()


# ---------------------------------------------------------------------------
# 查找平台对应的标签页
# ---------------------------------------------------------------------------
CDP_PORTS = [9222, 9223, 9224]  # 9222=Edge, 9223=Chrome, 9224=备用

def find_tab_for_platform(domain: str) -> dict | None:
    """通过 CDP 查找匹配平台域名的已有标签页（多端口扫描）"""
    for port in CDP_PORTS:
        try:
            resp = urllib.request.urlopen(f"http://localhost:{port}/json", timeout=3)
            tabs = json.loads(resp.read())
            for t in tabs:
                url = t.get("url", "")
                if domain in url and t.get("webSocketDebuggerUrl"):
                    return t
            # 放宽匹配：仅域名包含
            for t in tabs:
                url = t.get("url", "")
                if domain.split("/")[0] in url and t.get("webSocketDebuggerUrl"):
                    return t
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 单个平台提取
# ---------------------------------------------------------------------------
async def extract_one(name: str, titles: list[str]) -> list[dict]:
    cfg = PLATFORMS[name]

    tab = find_tab_for_platform(cfg["domain"])
    if not tab:
        print(f"  [{name}] 未找到标签页", flush=True)
        return []

    print(f"  [{name}] 找到标签页", flush=True)

    cdp = CDP()
    try:
        await cdp.connect_to_tab(tab)

        # 动态提取 token（公众号专用：从当前标签页 URL 获取实时 token）
        nav_url = cfg["nav_url"]
        if name == "公众号" and "{token}" in nav_url:
            current_url = await cdp.eval("window.location.href")
            tokens = re.findall(r'token=(\d+)', current_url)
            if tokens:
                nav_url = nav_url.replace("{token}", tokens[0])
                if cfg.get("fallback_url"):
                    cfg["fallback_url"] = cfg["fallback_url"].replace("{token}", tokens[0])
                print(f"  [{name}] 动态提取token: {tokens[0]}", flush=True)
            else:
                print(f"  [{name}] 未提取到token，使用原始URL", flush=True)

        # 导航到管理页
        await cdp.navigate(nav_url)
        print(f"  [{name}] 已导航", flush=True)

        # 等待 SPA 加载
        await asyncio.sleep(cfg["wait"])

        # 滚动
        await cdp.scroll_down()
        await asyncio.sleep(1)

        # 点击 tab（如"发表记录""作品管理"）
        clicked = False
        if cfg["click"]:
            clicked = await cdp.click_text(cfg["click"])
            if clicked:
                print(f"  [{name}] 已点击 [{cfg['click']}]", flush=True)
            else:
                # 如果没找到，尝试先点击上级菜单再试
                print(f"  [{name}] 尝试上级菜单...", flush=True)
                parent_clicks = cfg.get("parent_clicks", [])
                for pc in parent_clicks:
                    await cdp.click_text(pc)
                    await asyncio.sleep(2)
                clicked = await cdp.click_text(cfg["click"])
                if clicked:
                    print(f"  [{name}] 已点击 [{cfg['click']}]", flush=True)
                else:
                    print(f"  [{name}] 未找到 [{cfg['click']}]", flush=True)
            await asyncio.sleep(cfg["click_wait"])
        
        # 如果没点成功但有 fallback URL，直接导航过去
        if not clicked and cfg.get("fallback_url"):
            print(f"  [{name}] 尝试 fallback URL...", flush=True)
            await cdp.navigate(cfg["fallback_url"])
            await asyncio.sleep(cfg.get("wait", 6))

        # 提取
        result = await cdp.eval(cfg["extract_js"])
        if not result or result == "[]":
            # 滚动后重试
            await cdp.scroll_down()
            await asyncio.sleep(2)
            result = await cdp.eval(cfg["extract_js"])

        if not result or result == "[]":
            print(f"  [{name}] 未提取到文章", flush=True)
            return []

        articles = json.loads(result)

        # 标题匹配（支持模糊匹配）
        if titles:
            matched = []
            def _clean(s):
                for c in '，。、！？：；""''（）《》 \t\r\n-':
                    s = s.replace(c, '')
                return s
            for a in articles:
                t = a.get("title", "").strip().lower()
                t_clean = _clean(t)
                for expected in titles:
                    e = expected.strip().lower()
                    e_clean = _clean(e)
                    # 精确包含匹配
                    if e in t or t in e:
                        matched.append(a)
                        break
                    # 去标点后的包含匹配
                    if e_clean and (e_clean in t_clean or t_clean in e_clean):
                        matched.append(a)
                        break
                    # 前8个字匹配（标题开头一致即可）
                    if len(e) >= 8 and e[:8] in t:
                        matched.append(a)
                        break
            # 匹配0篇但有文章时，刷新页面重试一次
            if len(matched) == 0 and len(articles) > 0:
                print(f"  [{name}] 匹配0篇，刷新页面重试...", flush=True)
                await cdp.navigate(cfg.get("fallback_url") or cfg["nav_url"])
                await asyncio.sleep(cfg.get("wait", 6))
                result = await cdp.eval(cfg["extract_js"])
                if result and result != "[]":
                    articles = json.loads(result)
                    for a in articles:
                        t = a.get("title", "").strip().lower()
                        t_clean = _clean(t)
                        for expected in titles:
                            e = expected.strip().lower()
                            e_clean = _clean(e)
                            if e in t or t in e or (e_clean and e_clean in t_clean):
                                matched.append(a)
                                break
            print(f"  [{name}] {len(articles)} 篇, 匹配 {len(matched)} 篇", flush=True)
            return matched

        print(f"  [{name}] {len(articles)} 篇", flush=True)
        return articles[:10]

    except Exception as e:
        print(f"  [{name}] 错误: {e}", flush=True)
        return []
    finally:
        await cdp.close()


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
async def main_async(titles: list[str], target_date: str):
    print(f"标题: {titles or '(全部)'}")
    print(f"日期: {target_date}")
    print(f"共 {len(PLATFORM_ORDER)} 个平台, 全自动 CDP 提取...")
    print("=" * 50)

    results = {}
    for name in PLATFORM_ORDER:
        print(f"\n--- {name} ---")
        results[name] = await extract_one(name, titles)

    # 输出
    lines = [f"账号B+{target_date}"]
    for name in PLATFORM_ORDER:
        label = PLATFORM_LABELS.get(name, name)
        arts = results.get(name, [])
        if arts:
            for i, a in enumerate(arts):
                url = a["url"]
                for p in ["?token=", "?lang=", "?spm=", "?sharefrom="]:
                    if p in url:
                        url = url.split(p)[0]
                if i == 0:
                    lines.append(f"{label}\t{url}")
                else:
                    lines.append(f"\t{url}")
        else:
            lines.append(f"{label}\t（未获取到）")

    output = "\n".join(lines)
    print(f"\n\n{'='*50}")
    print(output)

    out_path = OUTPUT_DIR / f"links-{target_date}.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"\n已保存: {out_path}")
    print(f"请打开 outputs/links-{target_date}.md 查看结果")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="六平台链接汇总 CDP 版")
    parser.add_argument("--titles", default="", help="文章标题，逗号分隔")
    parser.add_argument("--date", default="", help="日期 YYYY-MM-DD")
    args = parser.parse_args()

    titles = [t.strip() for t in args.titles.split(",") if t.strip()]
    target_date = args.date or f"{date.today().month}.{date.today().day}"

    asyncio.run(main_async(titles, target_date))


if __name__ == "__main__":
    main()
