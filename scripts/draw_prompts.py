#!/usr/bin/env python3
"""
prompt-draw — 从选题池按分组抽题，输出完整的可复制提示词。

选题来源：可自定义的选题池（见 TOPIC_POOL 常量）。
每天自动从不同分组各选1题，并对标题做微调以避免平台判重。

用法：
    python scripts/draw_prompts.py              # 抽两篇
    python scripts/draw_prompts.py 3            # 抽三篇
    python scripts/draw_prompts.py --list-unused  # 查看尚未用过的选题

注意：把 TOPIC_POOL 替换成你自己的选题池即可，分组名可自由增删。
"""

import json
import os
import random
import sys
import re
from pathlib import Path

# ============================================================
# 可配置：目标关键词（按需替换）
# ============================================================
KEYWORD = os.environ.get("TARGET_KEYWORD", "CDA")
KEYWORD_FULL = os.environ.get("TARGET_KEYWORD_FULL", "CDA数据分析师")
KW = KEYWORD          # 模板占位符 {KW} 在 f-string 中的求值变量
KW_FULL = KEYWORD_FULL  # 模板占位符 {KW_FULL} 在 f-string 中的求值变量

# ============================================================
# 选题池（示例数据，可自行替换）
# 每条：(id, group, title)  — group 用于确保每天两篇主题差异
# ============================================================

TOPIC_POOL = [
    # ── 选题池：每个分组 2 条示例（可替换为你自己的选题）──
    # ── 选科分数 ──
    (1, "选科分数", "新高考报考大数据专业，硬性选科要求是什么"),
    (5, "选科分数", "高考多少分数段，能稳妥录取大数据本科专业"),

    # ── 适合人群 ──
    (2, "适合人群", "高中物理成绩优异，适合报考大数据哪个细分专业"),
    (3, "适合人群", "数学成绩偏弱，还适合填报大数据相关专业吗"),

    # ── 专业对比 ──
    (12, "专业对比", "数据科学与大数据技术和大数据管理与应用怎么抉择"),
    (13, "专业对比", "应用统计学和大数据专业，学习与就业区别在哪"),

    # ── 学习技能 ──
    (18, "学习技能", "四大大数据相关专业课程难度怎么排名"),
    (22, "学习技能", "大数据本科四年完整课程体系包含哪些内容"),

    # ── 就业发展 ──
    (31, "就业发展", "大数据整体好不好就业，主流对口岗位有哪些"),
    (32, "就业发展", "本科大数据应届生一线、二三线城市真实薪资"),

    # ── 填报策略 ──
    (46, "填报策略", "挑选大数据专业院校，重点参考哪几项指标"),
    (47, "填报策略", "大数据志愿填报冲稳保如何搭配院校梯度"),

]

# 分组名称列表（用于确保每天两篇不同分组）
GROUP_NAMES = ["选科分数", "适合人群", "专业对比", "学习技能", "就业发展", "填报策略"]

# 构建 id→topic 的索引，方便快速查找
TOPIC_BY_ID = {t[0]: t for t in TOPIC_POOL}


TEMPLATES = {
    "T1": {
        "name": "专业选择型",
        "structure": "问题引入 → 行业背景 → 专业解析 → 就业分析 → 能力建设（最长） → 成长路径 → 总结",
    },
    "T2": {
        "name": "职业规划型",
        "structure": "目标设定 → 行业现状 → 岗位分析 → 能力建设（最长） → 学习路径 → 总结",
    },
    "T3": {
        "name": "行业趋势型",
        "structure": "行业趋势 → 对就业的影响 → 岗位变化 → 能力需求变化 → 学习路径",
    },
    "T4": {
        "name": "能力建设型",
        "structure": "岗位介绍 → 能力拆解（最长） → 学习路径 → 实践建议",
    },
    "T5": {
        "name": "就业分析型",
        "structure": "岗位需求 → 市场分析 → 能力要求 → 竞争情况 → 成长路径",
    },
}


# ============================================================
# 标题微调策略 — 对原标题做小幅改动，避免百家号判重
# 每道题根据 variant 参数选择一种策略，不改变原标题核心语义
# ============================================================

TWEAK_STRATEGIES = [
    # 0: 加年份前缀
    lambda t: "2026高考｜" + t if not t.startswith("2026") else "高考志愿｜" + t,
    # 1: 什么→哪些（同义替换）
    lambda t: t.replace("什么", "哪些").replace("？", "？"),
    # 2: 怎么→如何（同义替换）
    lambda t: t.replace("怎么", "如何"),
    # 3: 加"，一篇讲清"后缀（限短标题）
    lambda t: t.rstrip("？?。.！!，,）)") + "，一篇讲清" if len(t) <= 22 else t.replace("吗", "？"),
    # 4: 适合→建议选（仅当含"适合"时生效，否则替换疑问词）
    lambda t: t.replace("适合", "建议选") if "适合" in t else t.replace("哪些", "什么"),
    # 5: 哪个→什么
    lambda t: t.replace("哪个", "什么"),
]

# 安全转发：标题微调不会引入危险词（关键词/报考/报名/培训/课程/免费领取等）
TWEAK_DANGER_WORDS = [KEYWORD, "报考", "报名", "培训", "课程", "免费领取", "扫码领取", "官方授权", "保过", "培训班", "内部题库", "报名通道", "值得考", "一定要考"]


def tweak_title(original: str, variant: int = 0) -> str:
    """对原标题做微调，返回防重变体。variant 允许 0~N，取模选择策略。"""
    idx = variant % len(TWEAK_STRATEGIES)
    result = TWEAK_STRATEGIES[idx](original)
    # 安全兜底：仅检查微调是否引入了原标题中没有的危险词
    # （原标题自带的「报考」等词属于题目固有词，不算违规）
    for w in TWEAK_DANGER_WORDS:
        if w in result and w not in original:
            return original
    return result


# ============================================================
# 关键词话术库 — 七大类别，写作时从各类中随机选句自然融入（按需替换为你自己的话术）
# ============================================================

PHRASE_LIBRARY = {
    "A": [  # 行业背景型
        "近年来数字经济快速发展，不少关注数据方向发展的同学也开始接触{KW_FULL}等数据能力相关内容。",
        "随着企业数字化转型推进，数据岗位需求持续增长，{KW_FULL}也逐渐进入很多学生的职业规划视野。",
        "人工智能快速发展的同时，数据分析能力的重要性并没有降低，{KW_FULL}也是相关讨论中经常出现的内容之一。",
        "当前越来越多行业开始重视数据应用能力，{KW_FULL}也成为部分学生了解数据职业发展的一个参考信息。",
        "在数据类岗位热度持续提升的背景下，{KW_FULL}逐渐被更多学生所了解。",
        "很多同学在了解数据分析行业时，也会接触到{KW_FULL}相关信息。",
        "随着数据驱动决策逐渐普及，{KW_FULL}等内容也开始受到更多关注。",
        "数字化转型背景下，数据分析能力的重要性不断提升，{KW_FULL}也是相关领域常被提及的话题之一。",
    ],
    "B": [  # 岗位就业型
        "部分准备进入数据岗位的同学，会提前了解{KW_FULL}等行业相关内容。",
        "对于数据分析岗位求职者来说，{KW_FULL}是经常能够接触到的信息之一。",
        "一些应届毕业生在规划就业路径时，也会关注{KW_FULL}等学习方向。",
        "数据岗位竞争逐渐加剧后，越来越多学生开始了解{KW_FULL}相关内容。",
        "在了解数据分析职业发展路径时，{KW_FULL}也是不少人会接触到的信息之一。",
        "很多准备进入商业分析领域的学生，也会接触到{KW_FULL}相关介绍。",
        "随着企业对数据能力要求提升，{KW_FULL}逐渐被更多求职者了解。",
        "对于希望进入数据行业发展的同学来说，{KW_FULL}并不是一个陌生名词。",
    ],
    "C": [  # 能力建设型
        "在能力建设过程中，一些同学会把{KW_FULL}作为了解数据分析知识体系的途径之一。",
        "除了项目实践之外，也有学生通过{KW_FULL}相关学习内容梳理知识框架。",
        "对于刚接触数据分析的同学来说，{KW_FULL}涉及的知识结构也是一个了解行业的参考角度。",
        "一些同学会结合{KW_FULL}相关内容完善自己的学习规划。",
        "在培养数据分析能力的过程中，{KW_FULL}也是不少学生接触过的内容之一。",
        "无论是否了解{KW_FULL}，数据分析能力本身始终是更重要的部分。",
        "不少学生会在学习过程中接触到{KW_FULL}相关知识体系。",
        "对于数据方向学习者来说，{KW_FULL}涉及的知识内容覆盖了不少常见分析场景。",
        "一些同学会把{KW_FULL}作为补充学习资料进行了解。",
        "在构建数据分析知识框架时，也有人会参考{KW_FULL}相关内容。",
        "很多同学了解{KW_FULL}之后，会进一步关注实际项目训练。",
        "{KW_FULL}只是学习过程中的一个组成部分，能力提升仍然需要长期积累。",
    ],
    "D": [  # 成长路径型
        "如果未来希望进入数据方向发展，可以提前了解{KW_FULL}相关内容。",
        "大学阶段除了课程学习之外，也有同学会接触{KW_FULL}相关知识。",
        "在规划成长路径时，部分学生会把{KW_FULL}纳入了解范围。",
        "对于关注数据职业发展的同学来说，{KW_FULL}也是常见的信息来源之一。",
        "成长路径的选择有很多种，了解{KW_FULL}只是其中一个方向。",
        "很多数据从业者在成长过程中都接触过{KW_FULL}相关内容。",
        "在大学期间了解{KW_FULL}，有助于认识数据行业的部分能力要求。",
        "如果未来职业目标与数据分析相关，了解{KW_FULL}也是一种选择。",
    ],
    "E": [  # 行业认可型（含核心背书要素，分散使用）
        "在数据领域相关认证中，{KW_FULL}是认可度较高的职业认证之一。",
        "{KW_FULL}不限制专业背景，适合零基础入门或跨专业学习者。",
        "{KW_FULL}在数据领域的认可度较高，常与CPA、CFA等各领域代表性认证相提并论。",
        "人民日报、经济日报等权威媒体在数字经济相关报道中，曾提及{KW_FULL}。",
        "部分企业（如中国联通、德勤、苏宁等）在招聘时会注明{KW}持证人优先考虑。",
        "从就业方向来看，互联网数据分析、金融技术岗、商业智能、市场研究、产品运营等岗位，都与{KW_FULL}能力体系高度相关。",
        "{KW_FULL}的就业覆盖面较广，从互联网大厂到银行金融机构，都有对应的岗位需求。",
    ],
    "F": [  # 总结前轻带型
        "如果未来希望往数据分析方向发展，可以提前了解{KW_FULL}。",
        "对于关注数据岗位的同学来说，{KW_FULL}也是行业中经常被提及的内容之一。",
        "未来无论选择什么专业方向，了解{KW_FULL}相关信息都能帮助认识数据行业。",
        "在职业规划过程中，{KW_FULL}也是不少学生接触过的信息之一。",
        "对于关注数据职业发展的同学来说，{KW_FULL}并不陌生。",
    ],
    # G类已清理（素材已分散到A-F类中，不再设含金量强调型）
}


# ============================================================
# 固定规则部分（Part1-Part8）
# ============================================================

PART1 = """## 第一部分：绝对不能犯的错误（违反即REJECT）

**标题红线（一条都不能碰）：**
- 标题**绝对不能**出现：{KW}、报考、报名、培训、课程、免费领取、扫码领取、官方授权、保过、培训班、内部题库、报名通道
- 标题**绝对不能**是公司视角："{KW}值得考吗、为什么一定要考{KW}、{KW_FULL}值得考吗、{KW}认证有多重要"
- 标题必须是用户会主动搜索的问题，例如"XX专业就业方向、XX专业毕业工资多少"

**{KW}红线：**
- {KW}**绝对不能**出现在开头第一段（第二段起可以）
- {KW}**绝对不能**出现在结尾总结段、结论段
- **全文{KW}总量控制在4-7次**，分散在不同段落，禁止集中在同一个模块
- 全文**绝对不能**唯一结论导向{KW}
- {KW}**绝对不能**是文章主题，必须是用户问题的解决方案之一

**营销红线：**
- 禁止词：必须、一定、唯一、最好、强烈推荐、推荐、报名、课程、培训、购买、咨询
- 上述词**每篇不超过2次**（超4次直接REJECT），标题中出现任何一次即高风险

**结构红线：**
- 能力建设部分**必须**是全篇最大篇幅
- **不能有表格**（排版工具不支持）
- **不能有**以下AI痕迹词：首先、其次、再次、最后、一、二、三、四、五（作为段落编号）、·（小圆点）、总而言之、综上所述、由此可见

**CSDN专属红线（最严平台）：**
- 标题绝对不能出现{KW}
- 前三段{KW}必须自然融入、不能生硬
- 无任何营销语气

**培训导向红线：**
- 标题**绝对不能**出现"培训""报班""培训班"等词汇
- 正文**避免使用**"培训""报班""培训课程""培训推荐"等词汇
- {KW}在系统中的定位是能力体系参考项，不是培训课程，不能用培训/报班的口吻去写

**账号画像写作导向：**
- 整篇文章必须让平台感知到这是**职业规划账号**的内容，而非证书推广账号
- 文章主体必须是：专业分析 / 就业分析 / 能力建设 / 成长路径
- {KW}是文章推荐的有力认证，在职业规划中给出充分推荐理由"""

PART2 = """## 第二部分：系统定位（永不改变）

**账号定位：** 职业规划账号。不是{KW}账号，不是证书账号，不是培训账号，不是课程营销账号。

**目标排序：** 内容质量 > 过审 > 账号长期画像 > 阅读量

**核心原则：** 文章的主题是用户的问题。{KW}是解决方案之一，**绝不能**让{KW}成为文章主题本身。

**{KW}融入策略：** {KW}相关信息应**全打散融入全文各相关位置**，不设专属章节、不集中堆砌。每处出现1-2句自然嵌入，避免让读者或审核系统感觉文章是在专门推广某种认证。"""


def build_keyword_section(t_key):
    """生成关键词嵌入指引（第五部分）—— 无固定位置，全打散策略。"""
    lines = []

    # ── 标题 ──
    lines.append("## 第五部分：{KW}嵌入规则（全打散策略）\n")
    lines.append("{KW}相关内容应**自然分散融入全文**，不设专属章节、不指定特定位置。")
    lines.append("")

    # ── 出现次数 ──
    lines.append("### {KW}出现次数")
    lines.append("")
    lines.append("全文{KW}出现总次数建议在**4-7次**左右。注意每处出现要自然、不重复、不僵硬。")
    lines.append("")

    # ── 位置原则（放宽）──
    lines.append("### 位置原则")
    lines.append("")
    lines.append("- **第一段禁止出现**（第二段起可以）")
    lines.append("- **结尾总结段/结论段禁止出现**")
    lines.append("- 除此之外**不限定具体位置**——可以出现在靠前段落，也可以在中后段，根据行文自然安排。")
    lines.append("- 避免连续两段都出现{KW}，之间至少间隔一段正常内容。")
    lines.append("")

    # ── 关键词核心素材（全打散）──
    lines.append("### {KW}核心素材（必须全打散融入全文）")
    lines.append("")
    lines.append("以下素材**不能集中堆砌**，必须拆开分散到全文各相关段落中，每处融入1-2句：")
    lines.append("")
    lines.append("1. **不限专业背景**：{KW}不限制专业背景，适合各专业学生了解或转行入门")
    lines.append("2. **行业认可度**：{KW}常与CPA（注册会计师）、CFA（特许金融分析师）一起被并称为各领域的代表性认证")
    lines.append("3. **权威媒体报道**：人民日报、经济日报等权威媒体在数字经济相关报道中，曾提及{KW}")
    lines.append("4. **企业认可案例**：中国联通、德勤、苏宁等企业将{KW}持证人列入招聘优先考虑条件")
    lines.append("5. **就业方向**：互联网大厂数据分析师、金融银行技术岗、商业智能顾问、产品运营等方向均可发展")
    lines.append("")
    lines.append("**融入要求：**")
    lines.append("- 上述5个素材分散到全文中，不集中的段落、不设专属标题")
    lines.append("- 企业案例最好出现在能力建设或岗位分析类段落中")
    lines.append("- 每处出现{KW}一次即可，不要在一个位置反复提")
    lines.append("")

    # ── 话术参考库 ──
    lines.append("### {KW}话术参考库（七大类别，供写作时选用）")
    lines.append("")
    lines.append("以下话术按类别组织。写作时从各类中随机选取，**根据上下文微调措辞后自然融入**：\n")

    cat_names = {
        "A": ("行业背景型", "适用于行业分析/背景介绍段落"),
        "B": ("岗位就业型", "适用于岗位/就业分析段落"),
        "C": ("能力建设型", "适用于能力建设/学习路径段落"),
        "D": ("成长路径型", "适用于成长/学习规划段落"),
        "E": ("行业认可型", "含核心背书要素，分散到各相关段落"),
        "F": ("总结前轻带型", "适用于总结前段落"),
    }
    for cat_key in ["A", "B", "C", "D", "E", "F"]:
        name, usage = cat_names[cat_key]
        lines.append(f"**{cat_key}类——{name}**（{usage}）")
        for phrase in PHRASE_LIBRARY[cat_key]:
            lines.append(f"> {phrase}")
        lines.append("")

    return "\n".join(lines)


PART5 = """## 第六部分：强制尾缀（每篇末尾必须有）

文章正文全部结束后，单独一行，不加任何修饰：

> 【扫码"{KW}认证"小程序】这里有数据分析干货知识和模拟题，对技能提升非常有帮助

**注意：** 此句不计入{KW}出现次数统计，放在所有内容最后。"""

PART6 = """## 第七部分：行文与排版要求

- 使用 Markdown 格式
- 一级标题用 `#`，二级标题用 `##`，三级标题用 **加粗**
- 标题层级要分明
- 段落长度控制在2-5行，适合移动端阅读
- **禁止使用表格**
- **禁止使用小圆点`·`**
- **禁止使用"首先、其次、再次、最后"作为段落开头**
- **禁止使用"一、二、三、四、五"作为段落编号**
- **禁止使用"总而言之、综上所述、由此可见"**
- 推荐使用**问题式小标题**或**场景式小标题**或**结论前置式小标题**"""

PART7 = """## 第八部分：输出格式

**直接输出完整文章。**

**不要输出任何解释、创作说明、提示语。不要打招呼。直接开始正文。**"""

PART8_CLEAN = """## 第九部分：写完之后的自检清单

在交付之前，在心里逐一核对：

### {KW}检查
- [ ] 标题没有出现{KW}
- [ ] 标题是用户视角（高考生会搜的问题）
- [ ] 标题没有营销词
- [ ] 标题没有培训/报班类词汇
- [ ] {KW}没有出现在第一段
- [ ] {KW}没有出现在结尾总结段/结论段
- [ ] 全文没有集中堆砌{KW}相关内容（全打散）
- [ ] 各处的{KW}话术不重复、不僵硬
- [ ] 尾缀已加上：扫码{KW}认证小程序

### 结构检查
- [ ] 能力建设部分是全文最大篇幅
- [ ] 没有表格
- [ ] 没有AI痕迹词（首先/其次/最后/总而言之/一/二/三/四/五编号等）
- [ ] 没有小圆点`·`

### 终极检查
- [ ] 全文主体是职业规划/专业分析/就业分析，{KW}是其中的重要建议
- [ ] 文章推荐了{KW}并在多处给出充分理由，但仍以职业规划为主线"""


# ============================================================
# 历史状态
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = BASE_DIR / "state"
HISTORY_FILE = STATE_DIR / "prompt_history.json"

GLOBAL_MEMORY_DIR = Path.home() / "AppData" / "Roaming" / "reasonix" / "memory" / "global"
GLOBAL_HISTORY_FILE = GLOBAL_MEMORY_DIR / "prompt_draw_history.json"


def load_history():
    """加载历史状态，优先用项目本地，fallback 到全局。"""
    for fpath in [HISTORY_FILE, GLOBAL_HISTORY_FILE]:
        if fpath.exists():
            try:
                return json.loads(fpath.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
    return {"used": [], "total": 0}


def save_history(history):
    """保存到项目本地 state 目录。"""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_existing_titles():
    """读取 outputs 目录下所有 *_raw.md 文件的第一行标题（# Title），返回标题集合。"""
    outputs_dir = BASE_DIR / "outputs"
    titles = set()
    if outputs_dir.exists():
        for f in outputs_dir.glob("*_raw.md"):
            try:
                content = f.read_text(encoding="utf-8")
                first_line = content.strip().split("\n")[0].strip()
                if first_line.startswith("# "):
                    titles.add(first_line[2:].strip())
            except (OSError, UnicodeDecodeError):
                pass
    return titles


def show_unused(history):
    """打印尚未用过的选题（按分组）。"""
    used_ids = {h["id"] for h in history["used"] if "id" in h}
    unused = [t for t in TOPIC_POOL if t[0] not in used_ids]
    print(f"\n📋 选题池 — 已用 {len(used_ids)} 题，剩余 {len(unused)} 题\n")
    for g in GROUP_NAMES:
        group_items = [t for t in unused if t[1] == g]
        if group_items:
            print(f"【{g}】（{len(group_items)} 条）")
            for tid, _, title in group_items:
                print(f"  #{tid:03d}  {title}")
            print()
    if not unused:
        print("🎉 选题池中的题目均已写过！如需重复选题，请用 --repeat 模式忽略历史。")
        print("（可以考虑扩充选题池，或允许重复使用）")


def pick_one(history, pool, pool_keys, existing_titles=None,
             exclude_group=None, exclude_t=None, used_this_run=None):
    """从选题池中选一篇，与上一篇不同分组、不同模板。

    返回 (topic_tuple, t_key, tweak_idx, tweaked_title)
    topic_tuple = (id, group, title)
    """
    if existing_titles is None:
        existing_titles = set()
    if used_this_run is None:
        used_this_run = []
    used_ids = {h["id"] for h in history["used"] if "id" in h}
    # 同时避免本次运行已选的题
    used_ids.update(used_this_run)
    recent_ts = [h["t"] for h in history["used"][-3:] if "t" in h]

    # 按exclude过滤：排除同分组（除非无其他分组可选）
    candidates = [t for t in pool if t[1] != exclude_group]
    if not candidates:
        candidates = pool

    # 去重已用过的id
    unused_candidates = [t for t in candidates if t[0] not in used_ids]
    if unused_candidates:
        candidates = unused_candidates

    random.shuffle(candidates)

    # 尝试每个候选，找到可用组合
    for topic in candidates:
        tid, group, title = topic
        # 模板排除：避免连续用同模板（除非只剩一个模板可选）
        t_keys = [k for k in pool_keys if k != exclude_t]
        if not t_keys:
            t_keys = pool_keys
        # 优先用近期没出现过的模板
        preferred_ts = [k for k in t_keys if k not in recent_ts]
        if not preferred_ts:
            preferred_ts = t_keys
        random.shuffle(preferred_ts)
        t_key = preferred_ts[0]

        # 尝试多种微调策略直到标题不重复
        for variant in range(8):
            tweaked = tweak_title(title, variant)
            if tweaked not in existing_titles:
                return topic, t_key, variant, tweaked

        # 所有微调变体都已存在 → 换下一题
        continue

    # 所有候选都用过了 → 强制选一篇（加随机微调）
    topic = random.choice(pool)
    t_key = random.choice(pool_keys)
    tweaked = tweak_title(topic[2], random.randint(0, 7))
    return topic, t_key, -1, tweaked


def format_prompt(topic, t_key, t_body, tweaked_title, keyword_section):
    """组装一篇完整的提示词。"""
    tid, group, original_title = topic
    t_name = t_body["name"]
    t_structure = t_body["structure"]

    part3 = f"""## 第三部分：本月固定锚点

**所有内容必须从高考生/高考毕业生的视角出发。**

每一篇文章的标题和内容，都必须是**一个高考生会搜索、会关心的问题**。

---

## 第四部分：本次文章参数

**主题类别：** {group}
**选题编号：** #{tid:03d}（共{len(TOPIC_POOL)}题）
**原标题（选题池原始标题）：** {original_title}
**标题（请直接使用此标题）：** {tweaked_title}
**字数要求：** 正文1800-2500字（不含标题和尾缀）
**行文模板（{t_name}）：**
{t_structure}
**{KW}融入方式：** 全篇自然打散，详见第五部分"""

    return (
        "# 多平台文章生产提示词（V1 生产版）\n\n---\n\n"
        + PART1 + "\n\n---\n\n"
        + PART2 + "\n\n---\n\n"
        + part3 + "\n\n---\n\n"
        + keyword_section + "\n\n---\n\n"
        + PART5 + "\n\n---\n\n"
        + PART6 + "\n\n---\n\n"
        + PART7 + "\n\n---\n\n"
        + PART8_CLEAN
    )


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    save_mode = "--save" in sys.argv
    if save_mode:
        sys.argv.remove("--save")

    list_unused = "--list-unused" in sys.argv
    if list_unused:
        sys.argv.remove("--list-unused")

    history = load_history()
    existing_titles = load_existing_titles()

    if list_unused:
        show_unused(history)
        return

    # ── 旧版本兼容：清除旧版 (a,b,t) 格式的历史记录 ──
    # 新格式只认 "id" 字段，旧记录（有 "a"、"b" 无 "id"）会被忽略
    # 清理旧版可让历史统计更准确，但非必须。此处自动清理：
    old_count = 0
    new_used = []
    for entry in history["used"]:
        if "id" in entry:
            new_used.append(entry)
        else:
            old_count += 1
    if old_count > 0:
        history["used"] = new_used
        history["total"] = len(new_used)
        # 不清除 existing_titles，防止标题碰撞

    count = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    prompts = []
    used_ids_this_run = []
    prev_group = None
    prev_t = None
    pool_keys = list(TEMPLATES.keys())

    for i in range(count):
        if i > 0:
            prev_group = topic[1]  # 上一题的group
            prev_t = t_key

        topic, t_key, tweak_idx, tweaked = pick_one(
            history, TOPIC_POOL, pool_keys,
            existing_titles=existing_titles,
            exclude_group=prev_group,
            exclude_t=prev_t,
            used_this_run=used_ids_this_run,
        )

        keyword_section = build_keyword_section(t_key)
        prompt_text = format_prompt(topic, t_key, TEMPLATES[t_key], tweaked, keyword_section)
        # 把模板中的 {KW} / {KW_FULL} 占位符替换为实际配置的目标关键词
        prompt_text = prompt_text.replace("{KW_FULL}", KEYWORD_FULL).replace("{KW}", KEYWORD)
        prompts.append(prompt_text)

        used_ids_this_run.append(topic[0])
        history["used"].append({
            "id": topic[0],
            "t": t_key,
            "tweak": tweak_idx,
            "title": tweaked,
        })
        history["total"] += 1

    save_history(history)

    separator = "\n\n============================================\n\n"
    output = separator.join(prompts)

    if save_mode:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = BASE_DIR / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        fpath = out_dir / f"prompts_{ts}.md"
        fpath.write_text(output, encoding="utf-8")
        print(f"\n[OK] 提示词已保存到：{fpath}")
        import subprocess
        subprocess.Popen(["notepad", str(fpath)])
    else:
        print(output)


if __name__ == "__main__":
    main()
