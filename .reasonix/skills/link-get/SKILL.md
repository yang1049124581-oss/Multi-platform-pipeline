---
name: link-get
description: 五平台已发布文章链接自动汇总（公众号/头条号/百家号/知乎/CSDN）
---

# link-get —— 五平台文章链接自动汇总

> ⚠️ **强制路由**：用户说"整理链接/汇总链接/总结链接/今天的链接"时，必须先 `read_skill("link-get")` 加载本指令再执行，不得自行猜测跳过。

## 工作流程

```
① 问标题 → ② 预检CDP(Chrome+Edge双端口) → ③ CDP不通则启动浏览器(不杀进程) → ④ 跑采集 → ⑤ 读结果展示
                                        │
                          ├─ 缺平台标签页 → 只问缺的那个
                          ├─ 公众号未采到 → 备选①刷新→②opencli→③问用户
```

---

### ① 问标题
直接问用户：**"今天发布了哪些文章？把标题给我"**

> 开始计时，记录开始时间。

### ② 预检 CDP + 5平台标签页

```bash
# 检查 CDP 是否在线（Chrome 9223 / Edge 9222 任一即可）
for port in 9222 9223; do
  result=$(curl -s http://127.0.0.1:$port/json 2>&1 | python -c "import sys,json; d=json.load(sys.stdin); print(f'OK: {len(d)} tabs')" 2>/dev/null)
  [ -n "$result" ] && echo "Port $port: $result" && break
done
```

不通 → ③。通了 → 检查5平台标签页（自动扫描两个端口）：

```bash
curl -s http://127.0.0.1:9222/json 2>/dev/null | python -c "
import sys,json;d=json.load(sys.stdin);u=[t.get('url','') for t in d]
c={'公众号':'mp.weixin.qq.com','头条号':'mp.toutiao.com','百家号':'baijiahao.baidu.com','知乎':'zhihu.com/creator','CSDN':'csdn.net'}
m=[n for n,dom in c.items() if not any(dom in x for x in u)]
print('ALL OK' if not m else 'MISSING: '+','.join(m))
" 2>/dev/null || echo "Port 9222 offline, trying 9223..." && curl -s http://127.0.0.1:9223/json 2>/dev/null | python -c "
import sys,json;d=json.load(sys.stdin);u=[t.get('url','') for t in d]
c={'公众号':'mp.weixin.qq.com','头条号':'mp.toutiao.com','百家号':'baijiahao.baidu.com','知乎':'zhihu.com/creator','CSDN':'csdn.net'}
m=[n for n,dom in c.items() if not any(dom in x for x in u)]
print('ALL OK' if not m else 'MISSING: '+','.join(m))
"
```

| 输出 | 行为 |
|------|------|
| `ALL OK` | 跳到④跑采集 |
| `MISSING: 公众号` | **只问这一个平台**，不全部问 |

### ③ 自启动浏览器（不杀进程）

**永远不杀任何浏览器进程。** CDP 不通时按顺序尝试：

#### 方式 A：启动 Chrome（推荐）
```bash
python -c "import subprocess,os; paths=[r'C:\Program Files\Google\Chrome\Application\chrome.exe',r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',os.path.join(os.environ.get('LOCALAPPDATA',''),r'Google\Chrome\Application\chrome.exe')]; exe=next((p for p in paths if os.path.exists(p)),None); subprocess.Popen([exe,'--remote-debugging-port=9223']); print('Chrome启动中...端口9223')"
```

等待端口就绪（最多15秒）：
```bash
python -c "import urllib.request,json,time; [print('OK') or exit(0) if (lambda: (urllib.request.urlopen('http://127.0.0.1:9223/json',timeout=2),True)()[1])() else None for _ in range(15)] or print('超时')" 2>/dev/null
```

#### 方式 B：启动 Edge（备选）
```bash
python -c "import subprocess,os; exe=next((p for p in [r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',os.path.join(os.environ.get('LOCALAPPDATA',''),r'Microsoft\Edge\Application\msedge.exe')] if os.path.exists(p)),None); subprocess.Popen([exe,'--remote-debugging-port=9222']); print('Edge启动中...端口9222')"
```

等待端口就绪（最多15秒）：
```bash
python -c "import urllib.request,json,time; [print('OK') or exit(0) if (lambda: (urllib.request.urlopen('http://127.0.0.1:9222/json',timeout=2),True)()[1])() else None for _ in range(15)] or print('超时')" 2>/dev/null
```

#### 方式 C：用户手动
如果自动启动失败，让用户通过桌面/任务栏快捷方式打开浏览器（快捷方式已带 `--remote-debugging-port` 参数）。

### ④ 跑采集脚本

```bash
python ".\scripts\cdp_collect.py" --titles "标题A,标题B"
```

脚本会自动扫描 9222(Edge) 和 9223(Chrome) 两个端口，找到匹配的平台标签页进行提取。

### ⑤ 读结果展示 + 汇报耗时

```bash
cat ".\outputs\links-$(date +%m.%d).md"
```

展示结果后，汇报总耗时：**"完成，共耗时 X 分 X 秒"**

输出格式：
```
账号A+6.28
公众号	https://mp.weixin.qq.com/s/xxx
	https://mp.weixin.qq.com/s/yyy
头条号	https://www.toutiao.com/item/xxx/
百家号	http://baijiahao.baidu.com/s?id=xxx
知乎	https://zhuanlan.zhihu.com/p/xxx
CSDN	https://blog.csdn.net/{authorId}/article/details/xxx
```

### ⑤-B 公众号备选（主采集失败时执行）

逐级执行，成功后停止：

| 优先级 | 方式 | 操作 |
|--------|------|------|
| ① | CDP刷新重试 | 刷新公众号页，等15秒，重提取，最多2次 |
| ② | **opencli-browser驱动** | `opencli browser gzh-bind unbind` → `opencli browser gzh-bind open "https://mp.weixin.qq.com/"` → `find --css "a[href*='/s/']"` → 匹配标题取href |
| ③ | 用户手动补 | 请用户从订阅号助手APP或后台复制链接 |

> ✅ **实测有效**：opencli 可直接从公众号首页提取链接（`a.weui-desktop-mass-appmsg__title`），不依赖发表记录页面。

---

## 错误处理

| 现象 | 应对 |
|------|------|
| CDP连接失败 | 浏览器未开调试端口 → 用③自动启动，或让用户通过桌面/任务栏快捷方式重开（已带调试参数） |
| `[平台名] 未找到标签页` | **只问这一个平台**要不要打开 |
| `匹配0篇` | 采集脚本已自动刷新重试一次；仍0篇请用户验证该平台是否有文章 |
| CSDN匹配0篇 | 可能authorId失效或链接格式变了 → 检查 `cdp_collect.py` 的extract_js |
| 公众号未获取到 | 自动走备选路径①→②→③ |

**⚠️ 核心原则：永远不杀任何浏览器进程。** 登录态比什么都重要，CDP连不上就让用户操作，我来不及做的事不强行做。

---

## 前置条件

1. Chrome 快捷方式已添加 `--remote-debugging-port=9223`（或 Edge 已添加 `--remote-debugging-port=9222`）
2. 浏览器中已打开5平台管理后台并保持登录
3. 用户告知当天发布文章的标题

## 项目文件

```
五平台运营/
├── scripts/cdp_collect.py       # 主力采集（CDP五平台，含多端口扫描+模糊匹配+自动重试）
├── start_chrome_debug.bat       # 启动Chrome调试端口（备用，不杀进程）
├── start_edge_debug.bat         # 启动Edge调试端口（备用，不杀进程）
├── outputs/links-YYYY-MM-DD.md  # 采集结果
└── .reasonix/skills/link-get/   # 本skill
```
