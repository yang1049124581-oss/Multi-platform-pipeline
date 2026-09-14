#!/usr/bin/env python3
"""
strip_wechat_footer — 去除公众号专属的 CDA 扫码尾缀，生成适合其他平台的纯净版。

输入：{标题}_raw.md（包含 CDA 扫码尾缀文字）
输出：{标题}_clean.md（不含 CDA 扫码尾缀，适合头条/百家/知乎/CSDN 发布）

用法：
    python scripts/strip_wechat_footer.py outputs/{标题}_raw.md
    python scripts/strip_wechat_footer.py outputs/{标题}_raw.md -o outputs/{标题}_clean.md
    python scripts/strip_wechat_footer.py outputs/*_raw.md          # 批量处理

处理规则：
    1. 移除 "> 【扫码\"CDA认证\"小程序】..." 整行
    2. 移除 "@cda-random" 引用行
    3. 移除 "@8.jpg" 引用行
    4. 移除 "扫码了解CDA数据分析师认证..." 行
    5. 折叠多余的空白行
"""

import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"

# 需要移除的 CDA 尾缀相关正则
CLEANUP_PATTERNS = [
    # 扫码文字变体
    re.compile(r'^\s*>?\s*【扫码"CDA认证"小程序】[^\n]*\n?', re.MULTILINE),
    re.compile(r'^\s*>?\s*【扫码[「『]CDA认证[」』]小程序】[^\n]*\n?', re.MULTILINE),
    re.compile(r'^\s*扫码了解CDA数据分析师认证[^，]*，[^\n]*\n?', re.MULTILINE),
    re.compile(r'^\s*扫码了解CDA[^\n]*\n?', re.MULTILINE),
    re.compile(r'^\s*这里有数据分析干货知识和模拟题[^\n]*\n?', re.MULTILINE),
    # 图片引用
    re.compile(r'^\s*@cda-random\s*\n?', re.MULTILINE),
    re.compile(r'^\s*@8\.jpg\s*\n?', re.MULTILINE),
    # 其他可能的尾缀格式
    re.compile(r'^\s*\[扫码"CDA认证"小程序\][^\n]*\n?', re.MULTILINE),
    re.compile(r'^\s*——扫码了解CDA——[^\n]*\n?', re.MULTILINE),
]

# AI辅助创作声明（部分平台需要加，部分不加，作为注释让用户决定）
AI_DISCLAIMER = (
    "\n\n"
    "<!-- 以下声明仅供 AI 辅助创作标记，发布平台如要求声明请保留 -->\n"
    "<!-- 本文由 AI 辅助创作，经人工审核后发布 -->\n"
)


def strip_wechat_footer(text: str) -> str:
    """从文章正文中去掉公众号专属的 CDA 扫码尾缀。"""
    for pattern in CLEANUP_PATTERNS:
        text = pattern.sub('', text)

    # 折叠多余空白行（连续 3 个及以上换行 → 2 个）
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 去掉首尾空白
    text = text.strip()

    return text


def process_file(in_path: Path, out_path: Path = None) -> bool:
    """处理一个文件，返回是否成功。"""
    if not in_path.exists():
        print(f"[跳过] 文件不存在：{in_path}")
        return False

    content = in_path.read_text(encoding='utf-8')
    cleaned = strip_wechat_footer(content)

    if not cleaned.strip():
        print(f"[跳过] 文件清理后为空：{in_path.name}")
        return False

    # 默认输出路径：同目录下 _raw → _clean
    if out_path is None:
        stem = in_path.stem
        if stem.endswith('_raw'):
            stem = stem.replace('_raw', '_clean')
        else:
            stem = stem + '_clean'
        out_path = in_path.with_stem(stem)

    out_path.write_text(cleaned + '\n', encoding='utf-8')

    removed = len(content) - len(cleaned)
    print(f"  [OK] {in_path.name} → {out_path.name} （去除了 {removed} 字符）")
    return True


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0)

    files = []
    out_specified = None

    args = sys.argv[1:]
    while args:
        arg = args.pop(0)
        if arg == '-o' and args:
            out_specified = Path(args.pop(0))
        else:
            files.append(Path(arg))

    success = 0
    for fpath in files:
        if process_file(fpath, out_path=out_specified):
            success += 1
        # 如果指定了 -o，只处理第一个文件（后面的都用同一输出名会覆盖）
        if out_specified:
            break

    print(f"\n处理完成：{success}/{len(files)} 个文件成功")


if __name__ == '__main__':
    main()
