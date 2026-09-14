# 五平台内容运营自动化管线

一套跑通「**选题 → 写作 → 审核 → 排版 → 发布 → 链接汇总**」全链条的内容运营自动化工具，覆盖微信公众号 / 头条号 / 百家号 / 知乎 / CSDN 五个内容平台。

由 vibe coding 方式逐步搭建而成，结构上分为两层：

- **Python 脚本** —— 确定性的计算与浏览器操作（抽题、打分、渲染、CDP 采集）
- **AI Agent Skills**（`.reasonix/skills/`）—— 编排层，把脚本串成一句话触发的零请示流水线

---

## 全链条一览

| # | 环节 | 做什么 | 对应代码 |
|---|------|--------|----------|
| 1 | 选题 | 从选题池按分组抽 2 题（保证两篇主题差异）；自动跳过已写过的题；标题做同义微调避免平台判重 | `scripts/draw_prompts.py` |
| 2 | 写作 | AI 按抽出的提示词模板成文，遵守结构红线（无表格、无 AI 痕迹词、营销词限额等） | `article-push-workflow` skill |
| 3 | 审核 | 100 分制扣分引擎（标题危险词 / 关键词次数与位置 / 营销词 / AI 痕迹 / 结构完整性）；≥90 PASS，否则按规则库自动修复重审（≤5 轮） | `scripts/audit_article.py` |
| 4 | 排版 | 幂等合成：正文配图按章节自动插入、底部推广区自动追加；产出「带尾缀 / 无尾缀」两套版本 | `wechat_publisher.py compose` |
| 5 | 发布 | 渲染微信兼容内联样式 HTML → 图片自动上传微信 CDN → 官方 API 创建草稿（支持两篇一次推送） | `wechat_publisher.py prepare/draft/open` |
| 6 | 汇总 | CDP 直连已登录浏览器（Chrome 9223 / Edge 9222 双端口扫描），从五平台后台提取已发文章链接并汇总 | `scripts/cdp_collect.py` |

> 代码中出现的示例关键词（CDA）与审核阈值来自作者的实际使用场景，可自行全局替换成你的目标关键词。

## 目录结构

```
.
├── wechat_publisher.py            # 公众号排版发布主脚本（compose/prepare/draft/open/published）
├── scripts/
│   ├── draw_prompts.py            # 选题抽取（分组轮换 + 防重 + 标题微调）
│   ├── audit_article.py           # 文章审核打分引擎
│   ├── cdp_collect.py             # CDP 五平台链接汇总
│   ├── strip_wechat_footer.py     # 跨平台尾缀清理（生成纯净版）
│   ├── csdn_get.py                # CSDN 账号文章全量采集
│   ├── csdn_blog_link_grab.py     # CSDN 账号链接批量扒取
│   ├── render.mjs                 # Markdown → 微信 HTML 渲染入口（Node）
│   ├── wechat-renderer.mjs        # 渲染引擎（纯内联样式）
│   └── markdown-to-sections.mjs   # Markdown 结构解析
├── .reasonix/skills/              # AI 编排层（Reasonix 项目级 skills）
│   ├── article-push-workflow/     # 一键全流程：抽词→生成→审核→修复→排版→草稿
│   ├── prompt-draw/               # 单独抽提示词
│   ├── article-audit/             # 单独审核
│   ├── wechat-paiban/             # 公众号排版 + 两篇一次推送
│   └── link-get/                  # 链接汇总（含 CDP 预检、浏览器自启动）
├── start_chrome_debug.bat         # 以调试端口启动 Chrome（Windows）
├── start_edge_debug.bat           # 以调试端口启动 Edge（Windows）
├── collect_links.bat              # 链接汇总一键脚本（Windows）
├── .env.example                   # 凭据模板
└── requirements.txt
```

## 快速开始

**环境要求**：Python 3.10+、Node.js（排版渲染）、Chrome 或 Edge（平台后台需保持登录）。

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置凭据（仅公众号 API 发布需要）
cp .env.example .env    # 填入 AppID / AppSecret，并把本机出口 IP 加入公众号后台白名单

# 3. 以调试端口启动浏览器，并打开五个平台的管理后台保持登录
start_chrome_debug.bat   # 或 start_edge_debug.bat

# 4. 抽两套提示词（选题 + 模板 + 关键词分布）
python scripts/draw_prompts.py --save

# 5. 让 AI 按提示词成文，保存为 outputs/{标题}_raw.md 后审核
python scripts/audit_article.py outputs/{标题}_raw.md

# 6. 排版：合成配图 → 渲染 HTML → 创建公众号草稿
python wechat_publisher.py compose outputs/{标题}_raw.md outputs/{标题}_footer.md
python wechat_publisher.py prepare outputs/{标题}_footer.md
python wechat_publisher.py draft outputs/draft_config.json
python wechat_publisher.py open

# 7. 各平台发布完成后，汇总链接
python scripts/cdp_collect.py --titles "标题1,标题2"
```

若使用支持 skills 的 AI Agent（如 Reasonix），把 `.reasonix/skills/` 放在项目根目录，直接说「开始推送」即可触发全流程。

## 设计要点

**不可变文件管线**：`_raw.md`（源稿，只读）→ `_composed.md`（合成稿，可重新生成）→ `_composed.html`（成品）。compose 永远读源稿、写新文件，跑 100 次结果一致，不会叠加图片或尾缀。

**不杀浏览器进程**：所有浏览器自动化复用你已登录的标签页（CDP 连接），宁可人工补一步也不清登录态——登录态是这类运营自动化的最大资产。

**审核-修复闭环**：审核输出结构化问题清单，AI 按规则库逐条修复后重审，最多 5 轮；修复历史落盘积累，用于迭代规则。

**发布边界**：公众号走官方 API 全自动到草稿箱；其余四平台刻意保持人工发布，只共享排版产物，避免触发平台风控。

## 适配自己的场景

| 想改什么 | 改哪里 |
|----------|--------|
| 选题池 | `scripts/draw_prompts.py` 顶部 `TOPIC_POOL`（含分组定义） |
| 目标关键词与红线规则 | `scripts/audit_article.py` 顶部常量区 |
| 底部推广区文案/图片 | `wechat_publisher.py` 的 `_cda_bottom_block()` |
| 平台列表 / 提取规则 | `scripts/cdp_collect.py` 的 `PLATFORMS` |

## 说明

- `scripts/render.mjs`、`wechat-renderer.mjs`、`markdown-to-sections.mjs` 为第三方微信排版渲染引擎的衍生版本（上游详见 `render.mjs` 文件头注释），使用前请自行核实上游许可。
- 本仓库不含任何运营内容、账号数据与凭据，仅保留通用工具代码。

## License

MIT
