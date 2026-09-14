#!/usr/bin/env python3
"""
article-audit — 多平台文章审核引擎（关键词露出 / 风险词 / AI 痕迹 / 结构完整性）

用法：
    cat article.md | python scripts/audit_article.py          # 从 stdin 读
    python scripts/audit_article.py outputs/article1.md        # 从文件读
    python scripts/audit_article.py outputs/a.md outputs/b.md  # 多文件

评分体系：
    初始 100 分，仅扣分项（无加分项）。
    PASS  ≥ 90（可发布）
    < 90 = 改（需修复后重审）
    单模块扣分 ≥ 16 → HIGH RISK（建议人工查看）

审核依据：文件顶部常量区的可配置规则（关键词、风险词、评分阈值）
"""

import os
import re
import sys
from pathlib import Path

# ============================================================
# 模块一：常量定义
# ============================================================

# ── 高风险营销词（审核打分规则汇总.txt §五）
# 每出现一次 -5，同一个词超过 4 次 REJECT
HIGH_RISK_MARKETING = [
    "必须", "一定", "唯一", "最好",
    "强烈推荐", "推荐",
    "报名", "课程", "培训",
    "购买", "咨询",
]

# ── AI 痕迹词 ──
AI_TRACE_WORDS = [
    "首先", "其次", "再次", "最后",
    "总而言之", "综上所述", "由此可见",
    "归根结底", "总体来看", "整体而言",
    "不可否认的是", "值得注意的是", "需要指出的是",
    "与此同时", "另一方面", "从某种意义上讲", "从长远来看",
]

# ── 可配置：目标关键词（按需替换）──
KEYWORD = os.environ.get("TARGET_KEYWORD", "CDA")
KEYWORD_PATTERN = re.compile(re.escape(KEYWORD))

# ── 标题危险词 ──
TITLE_DANGER_WORDS = [
    KEYWORD, "报考", "报名", "培训", "课程",
    "免费领取", "扫码领取", "官方授权", "保过",
    "培训班", "内部题库", "报名通道", "学习班",
]

# ── 公司视角短语（标题 -20）──
COMPANY_PERSPECTIVE = [
    "值得考吗", "一定要考", "有多重要", "报名入口",
    "认证有多重要", "官方推荐", "为什么一定要",
]

# ── 职业规划关键词（标题合规判定）──
CAREER_TITLE_KW = ["就业", "专业", "职业", "规划", "前景", "工资", "出路"]

# ── 结构必检模块（汇总表 §八：8个模块）──
STRUCTURE_KEYWORDS = ["问题引入", "行业背景", "专业分析", "就业分析",
                      "能力建设", "成长路径", "证书体系", "总结"]

# ── 结构关键词模糊匹配（标题中可能出现的变体）──
STRUCTURE_FUZZY = {
    "问题引入": ["问题", "引入", "困惑", "纠结", "选择"],
    "行业背景": ["行业", "背景", "趋势", "现状", "发展"],
    "专业分析": ["专业", "分析", "方向", "课程", "学科"],
    "就业分析": ["就业", "岗位", "工作", "职业", "方向"],
    "能力建设": ["能力", "技能", "培养", "学习", "知识"],
    "成长路径": ["成长", "路径", "规划", "建议", "路线"],
    "证书体系": ["证书", "认证", "资格", "考试"],
    "总结": ["总结", "结语", "写在最后", "最后"],
}

# ── 证书池（M01 证书生态稀释检测）──
CERTIFICATE_POOL = [
    "CPA", "CFA", "证券从业", "基金从业", "教师资格",
    "法考", "法律职业资格", "四六级", "英语四六级",
    "雅思", "托福", "CATTI", "翻译资格",
    "一级建造师", "二级建造师", "一建", "二建",
    "执业医师", "护士资格", "普通话", "计算机二级",
    "PMP", "软考", "FRM",
]

# ── 证书模块五大要素关键词 ──
CERT_ELEMENTS = {
    "专业": ["不限专业", "零基础", "跨专业", "各专业"],
    "认可度": ["认可度", "认可", "CPA", "CFA", "代表性认证"],
    "媒体": ["人民日报", "经济日报", "权威媒体"],
    "企业": ["中国联通", "德勤", "苏宁", "央视广信", "银行", "金融机构"],
    "就业": ["就业方向", "数据分析师", "商业智能", "产品运营", "岗位"],
}

# ── 正则（KEYWORD_PATTERN 见文件顶部配置区）──
NUM_PREFIX = re.compile(r"^[一二三四五][、．\.\s]", re.MULTILINE)
BULLET_PATTERN = re.compile(r"[•·]")
TABLE_PATTERN = re.compile(r"\|.*\|.*\|")

# （审核打分规则汇总.txt 无营销句式检测）


# ============================================================
# 模块二：工具函数
# ============================================================

def _split_title_body(text):
    """分离标题和正文。"""
    lines = text.strip().split("\n")
    title, body_start = "", 0
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("# ") and not title:
            title = s.lstrip("# ").strip()
            body_start = i + 1
        elif s.startswith("# ") and title:
            break
    if not title:
        title = lines[0].strip() if lines else ""
        body_start = 1
    return title, "\n".join(lines[body_start:])


def _split_paragraphs(body):
    """将正文按空行分段，过滤空段。"""
    return [p.strip() for p in body.split("\n\n") if p.strip()]


def _find_cert_module(paragraphs):
    """定位证书规划模块，返回 (start_idx, end_idx) 或 None。"""
    for i, p in enumerate(paragraphs):
        for kw in ["证书", "认证", "资格", "规划"]:
            if kw in p and any(h in p for h in ["##", "**"]):
                end = min(i + 8, len(paragraphs))
                return i, end
    return None


def _check_cert_elements(text):
    """检查证书模块五大要素覆盖率。"""
    found = []
    for elem, keywords in CERT_ELEMENTS.items():
        if any(kw in text for kw in keywords):
            found.append(elem)
    return found


def _find_kw_paragraphs(paragraphs):
    """返回包含关键词的段落索引列表。"""
    return [i for i, p in enumerate(paragraphs) if KEYWORD_PATTERN.search(p)]


def _kw_content_ratio(paragraphs):
    """关键词内容占比（段落维度）。"""
    if not paragraphs:
        return 0
    kw_count = len(_find_kw_paragraphs(paragraphs))
    return kw_count / len(paragraphs) * 100



def _check_high_risk_marketing(body):
    """高风险营销词检测（审核打分规则汇总.txt §五）。
    每出现一次 -5，同一个词超过 4 次 → REJECT。
    返回 (violations, total_deduction, is_reject)
    """
    violations = []
    total = 0
    for word in HIGH_RISK_MARKETING:
        # 「一定」豁免：非营销语境
        if word == "一定":
            # 只统计独立"一定"出现次数（排除"一定程度上""具有一定"等）
            matches = re.findall(r'(?<![\u4e00-\u9fff])一定(?![\u4e00-\u9fff]?程度上|具有)', body)
            count = len(matches)
        else:
            count = body.count(word)

        if count > 0:
            penalty = count * 5
            violations.append((word, count, penalty))
            total += penalty
            if count > 4:
                return violations, total, True  # is_reject
    return violations, total, False


# ============================================================
# 模块三：审核引擎
# ============================================================

def run_audit(text, filename="<stdin>"):
    """
    执行完整审核。

    返回 (result, score, issues, module_scores)
        result: "PASS" | "REJECT"
        score: 总分
        issues: 问题列表
        module_scores: 各模块扣分/加分明细
    """
    issues = []
    module_scores = {}  # {模块名: 扣分}
    score = 100

    def _deduct(module, amount, msg):
        nonlocal score
        score -= amount
        module_scores[module] = module_scores.get(module, 0) + amount
        issues.append(f"  {'❌' if amount >= 10 else '⚠️'} [{module}] {msg}")

    def _add(module, amount, msg):
        nonlocal score
        score += amount
        module_scores[module] = module_scores.get(module, 0) - amount  # 负值=加分
        issues.append(f"  ✅ [{module}] {msg}")

    def _note(msg):
        issues.append(f"  📌 {msg}")

    title, body = _split_title_body(text)
    paragraphs = _split_paragraphs(body)

    # ================================================================
    # M-TITLE 标题审核
    # ================================================================
    issues.append("【M-TITLE 标题审核】")

    # 危险词 → 直接 REJECT
    for word in TITLE_DANGER_WORDS:
        if word in title:
            issues.append(f"  ❌ 标题含危险词「{word}」→ REJECT")
            return "REJECT", 0, issues, module_scores

    # 公司视角 -20
    for phrase in COMPANY_PERSPECTIVE:
        if phrase in title.lower():
            _deduct("TITLE", 20, f"标题公司视角（含「{phrase}」） -20")
            break

    # 标题导向记录（不计分）
    if any(kw in title for kw in CAREER_TITLE_KW):
        _note("标题职业规划导向（合规）")
    if any(kw in title for kw in ["选专业", "怎么选", "选什么", "什么样的人"]):
        _note("标题专业选择导向（合规）")
    if any(kw in title for kw in ["能力", "技能", "学什么", "学习路径"]):
        _note("标题能力建设导向（合规）")

    # 培训/报名导向
    if any(kw in title for kw in ["培训", "报班"]):
        _deduct("TITLE", 40, "标题培训导向 -40")
    if "报名" in title:
        _deduct("TITLE", 50, "标题报名导向 -50")

    # ================================================================
    # M01 （无 — 审核打分规则汇总.txt 无证书生态稀释模块）
    # ================================================================

    # ================================================================
    # M02 营销词检测（审核打分规则汇总.txt §五）
    # ================================================================
    issues.append("【M02 营销词检测】")

    violations, total_penalty, is_reject = _check_high_risk_marketing(body)
    if is_reject:
        _deduct("M02", 100, f"高风险词「{violations[-1][0]}」出现 {violations[-1][1]} 次（>4）→ REJECT")
        return "REJECT", 0, issues, module_scores

    for word, count, penalty in violations:
        _deduct("M02", penalty, f"营销词「{word}」×{count} -{penalty}")

    if not violations:
        _note("未检测到高风险营销词")

    # ================================================================
    # M03 关键词露出检测
    # ================================================================
    issues.append(f"【M03 {KEYWORD}露出检测】")

    kw_count = len(KEYWORD_PATTERN.findall(body))
    _note(f"{KEYWORD} 全文出现次数：{kw_count}")

    # 1. 次数检测（审核打分规则汇总.txt §4.1）
    #   ≥5 且 <10：正常不扣分  |  ≥10：-10  |  ≥12：REJECT
    #   3-4：-5               |  ≤2：-15
    if kw_count >= 12:
        _deduct("M03", 100, f"{KEYWORD} 出现 {kw_count} 次（≥12）→ REJECT")
        return "REJECT", 0, issues, module_scores
    elif kw_count >= 10:
        _deduct("M03", 10, f"{KEYWORD} 出现 {kw_count} 次（≥10，偏多） -10")
    elif 5 <= kw_count < 10:
        _note(f"{KEYWORD} 出现 {kw_count} 次（正常范围）")
    elif 3 <= kw_count <= 4:
        _deduct("M03", 5, f"{KEYWORD} 仅出现 {kw_count} 次（偏低） -5")
    elif kw_count <= 2:
        _deduct("M03", 15, f"{KEYWORD} 仅出现 {kw_count} 次（严重不足） -15")

    # 2. 位置检测
    kw_para_indices = _find_kw_paragraphs(paragraphs)

    # 第一段（汇总表 §4.2：-20）
    if paragraphs and KEYWORD_PATTERN.search(paragraphs[0]):
        _deduct("M03", 20, f"{KEYWORD} 出现在第一段 -20")

    # 总结段（汇总表 §4.2：-20，排除尾缀）
    if paragraphs:
        last_idx = len(paragraphs) - 1
        last_para = paragraphs[last_idx]
        if "扫码" in last_para and "小程序" in last_para and last_idx > 0:
            last_para = paragraphs[last_idx - 1]
            last_idx = last_idx - 1
        if KEYWORD_PATTERN.search(last_para):
            _deduct("M03", 20, f"{KEYWORD} 出现在总结段 -20")

    # 前四段未出现
    first_four_has_kw = any(i < 4 for i in kw_para_indices)
    if kw_count > 0 and not first_four_has_kw:
        _deduct("M03", 7, f"前四段均未出现{KEYWORD}（内容审核风险） -7")

    # 首次出现位置
    if kw_para_indices:
        first_kw_idx = kw_para_indices[0]
        if first_kw_idx == 1:
            _note(f"{KEYWORD} 在第{first_kw_idx + 1}段首次出现（建议第3-5段）")
        elif 2 <= first_kw_idx <= 4:
            _note(f"{KEYWORD} 在第{first_kw_idx + 1}段首次出现（✅ 甜区位置）")
    elif kw_count == 0:
        _note(f"未检测到 {KEYWORD} 出现")

    # 3. 重复话术检测（汇总表 §4.3：每重复组 -10）
    kw_paras = [paragraphs[i] for i in kw_para_indices]
    unique_kw = set(kw_paras)
    if len(kw_paras) > 2 and len(unique_kw) < len(kw_paras):
        dup = len(kw_paras) - len(unique_kw)
        _deduct("M03", 10, f"{KEYWORD} 话术重复 {dup} 组 -10")

    # 4. 尾缀检测（汇总表 §十：未检测到→警告，不扣分）
    has_footer = any("扫码" in p and KEYWORD in p for p in paragraphs)
    if not has_footer:
        _note(f"⚠️ 尾缀「扫码{KEYWORD}认证小程序」缺失（建议补充）")
    else:
        _note("尾缀已存在")

    # ================================================================
    # M04 AI痕迹与排版排查（审核打分规则汇总.txt §六、§七）
    # ================================================================
    issues.append("【M04 AI痕迹与排版排查】")

    # 1. 小圆点（汇总表 §7.2：检测到 -5）
    bullet_hits = BULLET_PATTERN.findall(body)
    if bullet_hits:
        _deduct("M04", 5, f"小圆点 {len(bullet_hits)} 处 -5")

    # 2. 表格（汇总表 §7.1：检测到 -10）
    if TABLE_PATTERN.search(body):
        _deduct("M04", 10, "Markdown 表格 -10")

    # 3. AI 连接词与机械编号（汇总表 §六：每类词 -5）
    ai_total = 0
    ai_details = []
    for word in AI_TRACE_WORDS:
        cnt = body.count(word)
        if cnt > 0:
            ai_total += 5  # 每类词 -5
            ai_details.append(f"「{word}」×{cnt}")

    num_matches = NUM_PREFIX.findall(body)
    if num_matches:
        ai_total += 5  # 段落编号算一类
        ai_details.append(f"段落编号×{len(num_matches)}")

    if ai_total > 0:
        _deduct("M04", ai_total, f"AI痕迹词/段落编号：{', '.join(ai_details)} -{ai_total}")

    if not bullet_hits and not TABLE_PATTERN.search(body) and ai_total == 0:
        _note("未检测到 AI 痕迹或排版问题")

    # ================================================================
    # M05 结构完整性检测（审核打分规则汇总.txt §八）
    # ================================================================
    issues.append("【M05 结构完整性检测】")

    headings = re.findall(r"^#{1,3}\s+(.+)", body, re.MULTILINE)
    heading_text = "\n".join(headings)

    # 1. 统计各模块在标题中的覆盖情况
    # 检查方式：看每个h2/h3标题是否匹配该模块的模糊关键词
    matched_modules = []
    for module in STRUCTURE_KEYWORDS:
        fuzzy_kw = STRUCTURE_FUZZY[module]
        if any(kw in heading_text for kw in fuzzy_kw):
            matched_modules.append(module)

    missing_modules = [m for m in STRUCTURE_KEYWORDS if m not in matched_modules]
    missing_count = len(missing_modules)

    _note(f"已检测到模块：{'、'.join(matched_modules) if matched_modules else '(无)'}")
    if missing_modules:
        _note(f"未检测到模块：{'、'.join(missing_modules)}")

    # 2. 扣分/否决（汇总表 §八）
    if "能力建设" in missing_modules:
        # 再确认一遍正文是否真的没有能力相关内容
        has_capability = any(kw in body for kw in ["能力", "技能", "学习路径", "知识体系"])
        if not has_capability:
            _deduct("M05", 100, "缺少能力建设相关内容 → REJECT")
            return "REJECT", 0, issues, module_scores

    if missing_count >= 3:
        _deduct("M05", 20, f"缺失 {missing_count} 个结构模块 -20")
    elif missing_count >= 1:
        _deduct("M05", 10, f"缺失 {missing_count} 个结构模块 -10")
    else:
        _note("结构模块完整（覆盖全部8个模块）")

    # 3. 证书背书完整性检查（汇总表 §4.5/4.6）
    # 检查证书规划模块或全文是否覆盖关键词五大背书要素
    cert_range = _find_cert_module(paragraphs)
    cert_text = body  # 如果没有独立证书模块，检查全文
    if cert_range:
        start, end = cert_range
        cert_text = "\n".join(paragraphs[start:end])

    elements_found = _check_cert_elements(cert_text)
    elem_count = len(elements_found)

    if elem_count <= 1:
        _deduct("M05", 30, f"{KEYWORD}背书要素仅覆盖 {elem_count}/5（严重不足） -30")
    elif elem_count == 2:
        _deduct("M05", 20, f"{KEYWORD}背书要素仅覆盖 {elem_count}/5（不足） -20")
    elif elem_count == 3:
        _note(f"⚠️ {KEYWORD}背书要素覆盖 {elem_count}/5（不足，建议补充到≥4）")
    elif elem_count >= 4:
        _note(f"{KEYWORD}背书要素覆盖 {elem_count}/5 ✅")
    else:
        _note(f"{KEYWORD}背书要素覆盖 {elem_count}/5")

    # ================================================================
    # 汇总判定
    # ================================================================

    # CSDN 专属提醒
    csdn_notes = []
    if KEYWORD_PATTERN.search(title):
        csdn_notes.append(f"CSDN: 标题含{KEYWORD}，将被拒稿")
    if kw_count <= 2:
        csdn_notes.append(f"CSDN: 前三段{KEYWORD}注意自然融入")
    if csdn_notes:
        issues.append("【🔶 CSDN 专属提醒】")
        for note in csdn_notes:
            issues.append(f"  {note}")

    # HIGH RISK 检测
    high_risk_modules = [m for m, d in module_scores.items() if d >= 16]

    # 模块扣分明细
    issues.append("【模块扣分明细】")
    for mod, deduction in sorted(module_scores.items()):
        if deduction < 0:
            issues.append(f"  {mod}: +{abs(deduction)}（加分）")
        elif deduction > 0:
            issues.append(f"  {mod}: -{deduction}")

    # 最终判定（PASS ≥ 90，否则一律 改）
    issues.append(f"\n📊 最终得分：{score}")
    if score >= 90:
        result = "PASS"
    else:
        result = "改"

    if high_risk_modules:
        issues.append(f"⚠️ HIGH RISK：{', '.join(high_risk_modules)} 单模块扣分 ≥16，建议人工查看")

    return result, score, issues, module_scores


# ============================================================
# 模块四：报告格式化
# ============================================================

def format_report(result, score, issues, filename, module_scores=None):
    """格式化审核报告。"""
    icon = "✅" if result == "PASS" else "✏️"

    lines = [
        f"\n{'='*50}",
        f"  {icon} 审核结果：{result}  |  总分：{score}",
        f"  文件：{filename}",
        f"{'='*50}",
    ]
    for issue in issues:
        lines.append(f"  {issue}")
    lines.append(f"{'='*50}\n")
    return "\n".join(lines)


# ============================================================
# 模块五：入口
# ============================================================

def main():
    sys.stdout.reconfigure(encoding="utf-8")

    if len(sys.argv) > 1:
        for fpath in sys.argv[1:]:
            text = Path(fpath).read_text(encoding="utf-8")
            result, score, issues, ms = run_audit(text, filename=fpath)
            print(format_report(result, score, issues, fpath, ms))
    else:
        text = sys.stdin.read()
        result, score, issues, ms = run_audit(text)
        print(format_report(result, score, issues, "<stdin>", ms))


if __name__ == "__main__":
    main()
