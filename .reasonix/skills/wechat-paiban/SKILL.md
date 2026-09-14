---
name: wechat-paiban
description: 微信公众号精致排版 + 两篇一次推送发布。用户说"排版"即自动走完compose→prepare→draft→open全流程，不再询问。基于 xiaonan0527/wechat-publisher 渲染引擎，去除页脚，支持完整标题
---

# wechat-paiban

## 触发指令

**⚠️ 前置条件：文章必须先通过 `article-audit` 审核（得分 ≥ 80 PASS），禁止跳过审核直接排版。**

用户说「排版」并提供已通过审核的文章（一篇或两篇）→ 自动执行完整工作流至创建草稿，**不再询问确认**。

| 用户输入 | 行为 |
|---------|------|
| 两篇文章 + 「排版」 | 各自 compose → prepare → 更新 draft_config → draft → open |
| 一篇文章 + 「排版」 | compose → prepare → 更新 draft_config（单篇）→ draft → open |
| 「打开草稿箱」 | open 打开浏览器 |

## 概述

基于 `xiaonan0527/wechat-publisher` 渲染引擎，在其基础上仅做三点改动：
1. 去除渲染引擎默认的页脚署名
2. 两篇文章合为一次推送（微信 API 多图文草稿）
3. 使用完整原标题

排版引擎本身完全保留原样，未修改渲染逻辑。

## 排版规格（xiaonan0527 引擎）

| 元素 | 样式 |
|------|------|
| 正文 | 17px，行高 1.75，字间距 0.5px |
| h2 | 20px 加粗 |
| h3 | 18px 加粗 |
| 加粗文字 | 随机荧光笔高亮效果 |
| 代码块 | macOS 红黄绿圆点 |
| 引用块 | 蓝色左边框 + 浅灰背景 |

## 图片引用

| 写法 | 效果 |
|------|------|
| `@1.png` | 正文配图1（compose 自动插入第1个h2章节后） |
| `@2.png` | 正文配图2（compose 自动插入第3个h2章节后） |
| `@3..png` | 正文配图3（compose 自动插入第5个h2章节后） |
| `@cda-random` | 底部随机配图（从候选池随机选一张，compose 自动追加到底部；标签名可在配置区修改） |
| `@8.jpg` | 底部固定二维码图（compose 自动追加在引导文字后） |

## ⚠️ 硬性规则：不可变文件管线

**黄金原则：源文件永不修改。**

| 状态 | 文件名后缀 | 说明 |
|------|-----------|------|
| 原始稿 | `_raw.md` | 你给我的原文，只读不写 |
| 合成稿 | `_composed.md` | compose 的输出，可随时重新生成 |
| 成品 | `_composed.html` | prepare 的输出 |

- compose 默认读取 `_raw.md`，输出 `_composed.md`，**不碰源文件**
- prepare 可以直接传 `_raw.md`，它会自动先 compose 再 prepare
- 合并或复制文件时，永远复制 `_raw.md`，不要复制已 compose 过的文件

> ❗ 之前图片重复的根因：复制了已 compose 的文件再 compose，导致图片插了两遍。
> 现在有了 `_raw → _composed` 隔离，不会再发生。

---

## 自动合成规则（`compose` 命令）

**输入**：原始 Markdown（`.md` 或 `_raw.md`，不包含任何 `@` 图片引用）
**输出**：`_composed.md`（自动插入所有图片 + 推广底部，**不修改源文件**）

| 步骤 | 操作 |
|------|------|
| ① 清除旧推广底部 | 去掉正文中已有 `@cda-random`、`@8.jpg`、扫码文字等，避免重复 |
| ② 清除旧图片 | 去掉已有 `@1.png` / `@2.png` / `@3..png`，防重复插入 |
| ③ 插入正文三图 | `@1.png` → 第1个 `##` 章节末尾；`@2.png` → 第3个 `##` 章节末尾；`@3..png` → 第5个 `##` 章节末尾 |
| ④ 追加推广底部 | `@cda-random`（随机4/6/7） → 引导文字 → `@8.jpg` |

> 💡 **幂等性保证**：compose 每次读取源文件（_raw），输出新文件（_composed）。跑 100 次结果都一样。不会叠加、不会覆盖。

底部最终效果：

底部最终效果：
```
@cda-random

扫码了解CDA数据分析师认证，这里有数据分析干货知识和模拟题，对技能提升非常有帮助

@8.jpg
```

## 项目文件

```
多平台运营/
├── wechat_publisher.py      # 主发布脚本
├── .env                     # 公众号 AppID/AppSecret
├── scripts/
│   ├── render.mjs           # 渲染包装器（去除页脚）
│   ├── wechat-renderer.mjs  # xiaonan0527 渲染引擎（未修改）
│   └── markdown-to-sections.mjs  # Markdown 解析器（未修改）
├── 配图8月/                  # 封面图库
└── outputs/                 # 文章输出
```

## 用法（完整工作流）

### ⚡ 自动模式（默认 — 用户说"排版"时的标准流程）

```bash
# 0. 根据文章实际标题保存（源文件永不修改）
#    例如标题「被调剂了但还是想学化工」→ 转专业还是辅修_raw.md
#    不要使用 article_1_raw.md 这种固定前缀

# 1. 各自合成（读取 {标题}_raw.md，输出 {标题}_composed.md）
python wechat_publisher.py compose outputs/{标题1}_raw.md
python wechat_publisher.py compose outputs/{标题2}_raw.md

# 2. 各自生成 HTML（也支持直接传 _raw.md，会自动先 compose）
python wechat_publisher.py prepare outputs/{标题1}_composed.md
python wechat_publisher.py prepare outputs/{标题2}_composed.md

# 3. 更新草稿配置
# 自动写入 outputs/draft_config.json

# 4. 创建草稿（两篇一次推送）— 不询问，直接执行
python wechat_publisher.py draft outputs/draft_config.json

# 5. 打开公众号后台检查
python wechat_publisher.py open
```

> ⚠️ **禁止**询问用户"是否创建草稿"——排版指令本身就包含了创建草稿的意图。

### 手动模式（需要单独控制某一步时）

```bash
# 单步执行示例（{标题} 替换为实际文章标题简称）
python wechat_publisher.py compose outputs/{标题}_raw.md     # 输出 {标题}_composed.md
python wechat_publisher.py prepare outputs/{标题}_composed.md  # 输出 {标题}_composed.html
python wechat_publisher.py prepare outputs/{标题}_raw.md       # 自动先 compose 再 prepare
python wechat_publisher.py draft outputs/draft_config.json
python wechat_publisher.py open
```

> 提示：`compose` 只需在首次编辑或内容大改后执行一次。日常改文案时直接改 Markdown 再 `prepare` 即可。
> **禁止**将两篇文章合并到一个 .md 文件后再拆分——推广底部会丢失。

draft config.json 格式（content_file 使用实际标题对应的文件名）：
```json
[
  {"title": "完整原标题", "content_file": "outputs/{标题1}_composed.html", "cover": "配图8月", "author": "账号A"},
  {"title": "完整原标题2", "content_file": "outputs/{标题2}_composed.html", "cover": "配图8月", "author": "账号A"}
]
```
