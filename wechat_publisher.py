#!/usr/bin/env python3
"""
微信公众号官方 API 发布工具
适用于未认证订阅号：可创建图文草稿、上传图片，草稿需在后台手动发布

用法：
  python wechat_publisher.py status               查看草稿箱状态
  python wechat_publisher.py upload <图片路径>     上传图片到微信 CDN
  python wechat_publisher.py draft <config.json>  根据配置创建草稿（两篇一次推送）
  python wechat_publisher.py open                 打开浏览器到公众号草稿箱
"""

import json
import os
import random
import subprocess
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')

APPID = os.environ.get('WECHAT_APPID')
APPSECRET = os.environ.get('WECHAT_APPSECRET')
BASE_URL = 'https://api.weixin.qq.com/cgi-bin'


def ensure_creds():
    if not APPID or not APPSECRET:
        print("[错误] 请在 .env 中设置 WECHAT_APPID 和 WECHAT_APPSECRET")
        sys.exit(1)


def get_token():
    ensure_creds()
    url = f'{BASE_URL}/token'
    params = {'grant_type': 'client_credential', 'appid': APPID, 'secret': APPSECRET}
    resp = requests.get(url, params=params, timeout=10)
    data = resp.json()
    if 'access_token' in data:
        return data['access_token']
    else:
        print(f"[错误] 获取 access_token 失败：{data}")
        print("提示：请确认已在公众号后台将本机 IP 加入 IP 白名单")
        sys.exit(1)


def upload_image(token, image_path):
    """上传图片到微信 CDN，返回图片 URL"""
    path = Path(image_path)
    if not path.exists():
        print(f"  [跳过] 图片不存在：{image_path}")
        return None

    url = f'{BASE_URL}/media/uploadimg'
    with open(path, 'rb') as f:
        resp = requests.post(
            url, params={'access_token': token},
            files={'media': (path.name, f, 'image/jpeg' if path.suffix.lower() in ('.jpg', '.jpeg') else 'image/png')},
            timeout=30
        )
    data = resp.json()
    if 'url' in data:
        print(f"  [OK] 图片上传成功：{path.name}")
        return data['url']
    else:
        print(f"  [失败] 图片上传失败：{data}")
        return None


def upload_material(token, image_path):
    """上传图片为永久素材，返回 media_id（用于封面）"""
    path = Path(image_path)
    if not path.exists():
        print(f"  [跳过] 封面图片不存在：{image_path}")
        return None

    url = f'{BASE_URL}/material/add_material'
    with open(path, 'rb') as f:
        resp = requests.post(
            url, params={'access_token': token, 'type': 'image'},
            files={'media': (path.name, f, 'image/jpeg' if path.suffix.lower() in ('.jpg', '.jpeg') else 'image/png')},
            timeout=30
        )
    data = resp.json()
    if 'media_id' in data:
        print(f"  [OK] 封面上传成功：{path.name}")
        return data['media_id']
    else:
        print(f"  [失败] 封面上传失败：{data}")
        return None


def cmd_status():
    """查看草稿箱状态"""
    token = get_token()
    url = f'{BASE_URL}/draft/batchget'
    resp = requests.post(url, params={'access_token': token},
                         json={'offset': 0, 'count': 10, 'no_content': 0}, timeout=10)
    data = resp.json()
    total = data.get('total_count', 0)
    print(f"\n[草稿箱] 共 {total} 篇草稿（仅显示前10条）")
    print("-" * 40)
    if total == 0:
        print("  (空)")
    else:
        for item in data.get('item', []):
            update_time = item.get('update_time', '')
            for news in item.get('content', {}).get('news_item', []):
                title = news.get('title', '无标题')
                print(f"  - {title}")


def cmd_upload():
    """上传图片"""
    if len(sys.argv) < 3:
        print("用法：python wechat_publisher.py upload <图片路径1> [图片路径2 ...]")
        sys.exit(1)

    token = get_token()
    for path in sys.argv[2:]:
        url = upload_image(token, path)
        if url:
            print(f"  URL: {url}")


def cmd_draft():
    """
    创建草稿（支持两篇一次推送）
    配置文件格式：
    [
        {
            "title": "文章标题",
            "content_file": "outputs/article1/content.html",
            "cover": "配图7月/xxx.jpg",
            "author": "作者"
        },
        ...
    ]
    """
    if len(sys.argv) < 3:
        print("用法：python wechat_publisher.py draft <config.json>")
        sys.exit(1)

    config_path = sys.argv[2]
    if not Path(config_path).exists():
        print(f"[错误] 配置文件不存在：{config_path}")
        sys.exit(1)

    with open(config_path, encoding='utf-8') as f:
        articles_config = json.load(f)

    if not articles_config:
        print("[错误] 配置文件为空")
        sys.exit(1)

    token = get_token()

    # 1. 上传封面图片并构建文章列表
    articles = []
    used_covers = set()  # 记录已用的封面，避免重复

    for i, art in enumerate(articles_config):
        print(f"\n[第{i+1}篇] {art.get('title', '无标题')}")

        # 上传封面：支持目录随机选取
        cover_media_id = None
        if 'cover' in art and art['cover']:
            cover_path = Path(art['cover'])
            if cover_path.is_dir():
                # 从目录随机选一张未用过的
                image_exts = {'.jpg', '.jpeg', '.png', '.bmp'}
                candidates = [p for p in cover_path.iterdir()
                              if p.suffix.lower() in image_exts and p.name not in used_covers]
                if not candidates:
                    # 所有图都用过了，重新允许全部
                    candidates = [p for p in cover_path.iterdir()
                                  if p.suffix.lower() in image_exts]
                if candidates:
                    chosen = random.choice(candidates)
                    used_covers.add(chosen.name)
                    print(f"  [封面] 从 {cover_path.name}/ 随机选取：{chosen.name}")
                    cover_media_id = upload_material(token, str(chosen))
                else:
                    print(f"  [警告] {cover_path.name}/ 目录下无可用图片")
            else:
                cover_media_id = upload_material(token, art['cover'])

        # 读取正文内容并处理 @图片 引用
        content = _load_and_process_content(token, art)

        articles.append({
            'title': art['title'],  # 保持原标题完整
            'content': content,
            'thumb_media_id': cover_media_id or '',
            'author': (art.get('author', '') or '')[:2],  # 作者名不超过 6 字节 ≈ 2 汉字
            'need_open_comment': 1,
            'only_fans_can_comment': 0,
            'is_ai_created': 1,  # 声明内容由AI生成（公众号后台"创作来源"选项）
        })

    # 2. 创建草稿（所有文章一次推送）
    print(f"\n[创建草稿] 共 {len(articles)} 篇，一次推送...")
    payload = {'articles': articles}
    resp = requests.post(
        f'{BASE_URL}/draft/add',
        params={'access_token': token},
        data=json.dumps(payload, ensure_ascii=False),
        headers={'Content-Type': 'application/json'},
        timeout=15
    )
    data = resp.json()
    if 'media_id' in data:
        media_id = data['media_id']
        print(f"\n{'='*50}")
        print(f"[OK] 草稿创建成功！")
        print(f"media_id: {media_id}")
        print(f"\n下一步操作：")
        print(f"  1. 打开浏览器检查草稿：")
        print(f"     python wechat_publisher.py open")
        print(f"  2. 在公众号后台预览、修改、发布")
        print(f"{'='*50}")

        # 持久化保存 media_id 和文章标题（供后续 update-draft 使用）
        state_dir = Path(__file__).parent / 'state'
        state_dir.mkdir(parents=True, exist_ok=True)
        state = {
            'media_id': media_id,
            'titles': [a.get('title', f'文章{i+1}') for i, a in enumerate(articles_config)],
            'config': articles_config,
            'timestamp': str(Path(__file__).parent / 'state'),
        }
        # 用时间戳防止覆盖
        import datetime
        state['timestamp'] = datetime.datetime.now().isoformat()
        state_file = state_dir / 'last_draft.json'
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"  [状态] 已保存到 {state_file}")
    else:
        print(f"\n[失败] 创建草稿失败：{data}")
        sys.exit(1)


def cmd_open():
    """打开浏览器到公众号草稿箱"""
    url = "https://mp.weixin.qq.com/cgi-bin/appmsg?action=list&type=10&begin=0&count=10"
    print(f"[打开] 公众号草稿箱...")
    try:
        if sys.platform == 'win32':
            os.startfile(url)
        elif sys.platform == 'darwin':
            subprocess.run(['open', url])
        else:
            subprocess.run(['xdg-open', url])
    except Exception as e:
        print(f"  自动打开失败，请手动访问：{url}")
        print(f"  错误：{e}")


# ---------- compose 自动合成（正文三图 + CDA底部） ----------

import re as _re


def _strip_cda_bottom(content):
    """清除正文中已有的 CDA 底部内容（仅清除文字和二维码图），避免重复"""
    content = _re.sub(r'^\s*@8\.jpg\s*$', '', content, flags=_re.MULTILINE)
    content = _re.sub(r'扫码了解CDA数据分析师认证[^，]*，[^\n]*', '', content)
    content = _re.sub(r'【扫码"CDA认证"小程序】[^\n]*', '', content)
    content = _re.sub(r'\n{3,}', '\n\n', content)
    return content.strip() + '\n'


def _insert_body_images(content):
    """
    在正文 h2 章节之间自动插入三张配图：
    - @1.png   → 第 1 个 h2 章节后
    - @2.png   → 第 3 个 h2 章节后
    - @3..png  → 第 5 个 h2 章节后
    """
    lines = content.split('\n')
    h2_positions = [i for i, l in enumerate(lines) if _re.match(r'^##\s+(?!##)', l)]

    # 按 h2 切分为段落块
    segments = []
    start = 0
    for pos in h2_positions:
        segments.append(lines[start:pos])
        start = pos
    segments.append(lines[start:])  # 最后一个 h2 至末尾

    insert_after = {1: '@1.png', 3: '@2.png', 5: '@3..png'}

    result = []
    for i, seg in enumerate(segments):
        result.extend(seg)
        if i in insert_after:
            result.append('')
            # 为 xiaonan0527 渲染器留空行，图片独立成段
            result.append(insert_after[i])
            result.append('')

    return '\n'.join(result)


def _cda_bottom_block():
    """生成 CDA 底部区域：引导文字 → 8.jpg（二维码）"""
    return (
        '\n'
        '扫码了解CDA数据分析师认证，这里有数据分析干货知识和模拟题，对技能提升非常有帮助\n'
        '\n'
        '@8.jpg\n'
    )


def cmd_compose():
    """
    自动合成文章：插入正文三图（可选加 CDA 底部区域）
    用法：
      python wechat_publisher.py compose <input.md> [output.md]           # 默认带 CDA 尾缀
      python wechat_publisher.py compose --no-footer <input.md> [output.md]  # 无 CDA 尾缀

    处理流程：
      1. 清除已有 CDA 底部（防重复）
      2. 在第 1/3/5 个 h2 章节后插入 @1.png / @2.png / @3..png
      3. 追加 CDA 底部区域（除非 --no-footer）
      4. 输出合成后的 Markdown
    """
    if len(sys.argv) < 3:
        print("用法：python wechat_publisher.py compose [--no-footer] <input.md> [output.md]")
        sys.exit(1)

    # 检查 --no-footer 标志
    no_footer = '--no-footer' in sys.argv
    # 过滤掉 --no-footer 以便定位文件名参数
    args = [a for a in sys.argv[2:] if a != '--no-footer']

    in_path = Path(args[0])
    if not in_path.exists():
        print(f"[错误] 文件不存在：{in_path}")
        sys.exit(1)

    out_path = Path(args[1]) if len(args) > 1 else in_path.with_stem(
        in_path.stem.replace('_raw', '_composed') if in_path.stem.endswith('_raw')
        else in_path.stem + '_composed'
    )

    content = in_path.read_text(encoding='utf-8')

    print(f"  [合成] 读取：{in_path.name} → 输出：{out_path.name}")

    # 1. 去除已有的 CDA 底部
    content = _strip_cda_bottom(content)
    print("  [合成] 已清除旧 CDA 底部")

    # 2. 去除已有的正文图片引用（防重复插入）
    content = _re.sub(r'^\s*@[123]\.\.?png\s*$', '', content, flags=_re.MULTILINE)
    content = _re.sub(r'^\s*@cda-random\s*$', '', content, flags=_re.MULTILINE)
    content = _re.sub(r'\n{3,}', '\n\n', content)
    print("  [合成] 已清除旧正文图片引用")

    # 3. 插入正文三图
    content = _insert_body_images(content)
    print("  [合成] 已插入 @1.png / @2.png / @3..png")

    # 4. 插入文末随机图（@cda-random 随机选 4/6/7.jpg），不算尾缀
    content += '\n\n@cda-random\n'
    print("  [合成] 已插入文末随机图 @cda-random")

    # 5. 追加 CDA 底部（除非指定 --no-footer）
    if no_footer:
        print("  [合成] --no-footer 模式，跳过 CDA 底部")
    else:
        content += _cda_bottom_block()
        print("  [合成] 已追加 CDA 底部（文字 + @8.jpg）")

    out_path.write_text(content, encoding='utf-8')
    print(f"\n[OK] 合成完成：{out_path}")


def cmd_add_footer():
    """
    给已 compose 过的文件追加 CDA 底部区域（用于同步后补回尾缀）
    用法：python wechat_publisher.py add-footer <composed_nofooter.md> [output.md]

    处理流程：
      1. 清除已有的 CDA 底部（防重复）
      2. 追加 CDA 底部：@cda-random → 文字 → @8.jpg
      3. 输出到指定文件（默认覆盖原文件，或输出到新文件）
    """
    if len(sys.argv) < 3:
        print("用法：python wechat_publisher.py add-footer <input.md> [output.md]")
        sys.exit(1)

    in_path = Path(sys.argv[2])
    if not in_path.exists():
        print(f"[错误] 文件不存在：{in_path}")
        sys.exit(1)

    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else in_path

    content = in_path.read_text(encoding='utf-8')
    print(f"  [加尾缀] 读取：{in_path.name} → 输出：{out_path.name}")

    # 1. 清除已有的 CDA 底部（防重复）
    content = _strip_cda_bottom(content)

    # 2. 追加 CDA 底部
    content += _cda_bottom_block()

    out_path.write_text(content, encoding='utf-8')
    print(f"  [加尾缀] 已追加 CDA 底部（文字 + @8.jpg）")
    print(f"\n[OK] 已加回尾缀：{out_path}")


def cmd_update_draft():
    """
    更新已有草稿内容（把尾缀补回已同步的草稿）
    用法：
      python wechat_publisher.py update-draft <media_id> <html1> [html2]
      python wechat_publisher.py update-draft                      # 从 state/last_draft.json 读取 media_id

    注意：
      - 微信 API draft/update 对未认证订阅号可能不可用
      - 不可用时自动降级：创建新草稿 + 提示手动删除旧草稿
    """
    token = get_token()
    state_file = Path(__file__).parent / 'state' / 'last_draft.json'

    # 确定 media_id
    media_id = None
    html_files = []

    if len(sys.argv) >= 3:
        media_id = sys.argv[2]
        html_files = sys.argv[3:]
    elif state_file.exists():
        state = json.loads(state_file.read_text(encoding='utf-8'))
        media_id = state.get('media_id')
        print(f"  [更新] 从 state/last_draft.json 读取 media_id: {media_id}")

    if not media_id:
        print("[错误] 请提供 media_id，或确保 state/last_draft.json 存在")
        print("用法：python wechat_publisher.py update-draft <media_id> <html1> [html2]")
        sys.exit(1)

    if not html_files:
        print("[错误] 请提供至少一个 HTML 文件路径")
        sys.exit(1)

    # 读取 HTML 内容
    articles = []
    for i, hf in enumerate(html_files):
        hp = Path(hf)
        if not hp.exists():
            print(f"[错误] HTML 文件不存在：{hp}")
            sys.exit(1)
        content_html = hp.read_text(encoding='utf-8')
        # 尝试从 state 中读取原标题
        title = f"文章{i+1}"
        if state_file.exists():
            state = json.loads(state_file.read_text(encoding='utf-8'))
            titles = state.get('titles', [])
            if i < len(titles):
                title = titles[i]
        articles.append({
            'title': title,
            'content': content_html,
        })

    # 尝试 draft/update API
    print(f"\n[更新草稿] media_id: {media_id}")
    payload = {
        'media_id': media_id,
        'articles': articles,
        'index': 0,  # 从第 0 篇开始替换（两篇一次的情况 index 0 覆盖全部）
    }
    try:
        resp = requests.post(
            f'{BASE_URL}/draft/update',
            params={'access_token': token},
            data=json.dumps(payload, ensure_ascii=False),
            headers={'Content-Type': 'application/json'},
            timeout=15
        )
        data = resp.json()
        if data.get('errcode') == 0:
            print(f"\n{'='*50}")
            print(f"[OK] 草稿更新成功！media_id: {media_id}")
            print(f"{'='*50}")
            return
        else:
            errcode = data.get('errcode')
            errmsg = data.get('errmsg', '')
            print(f"\n[警告] draft/update API 返回错误：errcode={errcode}, errmsg={errmsg}")

            if errcode == 48001:  # API 无权限
                print("  -> 未认证订阅号不支持 draft/update API")
            elif errcode == 45057:  # media_id 不存在
                print("  -> media_id 已过期或不存在")
            else:
                print(f"  -> 未知错误")

            # 降级：创建新草稿
            print("\n[降级] 改为创建新草稿（带尾缀），请在后台手动删除旧草稿")
    except Exception as e:
        print(f"\n[错误] API 请求失败：{e}")
        print("\n[降级] 改为创建新草稿（带尾缀）")

    # --- 降级路径：创建新草稿 ---
    print("\n[创建新草稿] 生成带尾缀的新草稿...")

    # 从 state 读取原草稿配置
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding='utf-8'))
        config = state.get('config', [])
    else:
        config = []
        for i, hf in enumerate(html_files):
            config.append({
                'title': f"文章{i+1}",
                'content_file': str(hf),
                'cover': '配图8月',
                'author': '账号A',
            })

    # 更新 content_file 为传入的 HTML（带尾缀版本）
    for i, art in enumerate(config):
        if i < len(html_files):
            art['content_file'] = str(Path(html_files[i]).resolve())

    # 写入临时 config
    import tempfile
    tmp_config = Path(tempfile.mktemp(suffix='.json'))
    tmp_config.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')

    # 调用已有 draft 命令
    old_argv = sys.argv[:]
    sys.argv = ['wechat_publisher.py', 'draft', str(tmp_config)]
    try:
        cmd_draft()
    finally:
        sys.argv = old_argv
        if tmp_config.exists():
            tmp_config.unlink()

    print(f"\n[提示] 请手动删除旧的草稿（media_id: {media_id}）")


# ---------- 图片替换功能 ----------

IMG_PATTERN_CACHE = {}  # 缓存已上传的图片 CDN URL


def resolve_image_ref(token, ref):
    """
    解析图片引用：@文件名 或 相对路径
    自动上传到微信 CDN 并返回 URL
    缓存结果避免重复上传
    """
    ref = ref.strip()
    if ref in IMG_PATTERN_CACHE:
        return IMG_PATTERN_CACHE[ref]

    # 搜索可能的位置
    search_paths = [
        Path(ref),
        Path('.') / ref,
        Path('配图7月') / ref,
        Path('配图8月') / ref,
        Path('outputs') / ref,
    ]
    # 如果文件名是 @xxx.png 格式，去掉 @
    clean_ref = ref.lstrip('@')
    if clean_ref != ref:
        search_paths = [
            Path(clean_ref),
            Path('.') / clean_ref,
            Path('配图7月') / clean_ref,
            Path('配图8月') / clean_ref,
        ]

    found = None
    for p in search_paths:
        if p.exists():
            found = p
            break

    if not found:
        print(f"  [警告] 找不到图片: {ref}，跳过")
        IMG_PATTERN_CACHE[ref] = None
        return None

    url = upload_image(token, str(found))
    IMG_PATTERN_CACHE[ref] = url
    return url


def process_content_images(token, content):
    """
    扫描正文中的 @图片名 引用，自动上传并替换为 CDN URL
    支持：@1.png @2.png @3..png @配图7月/xxx.jpg
    特殊标签：@cda-random → 从 4.png/6.png/7.jpg 随机选一张
    """
    import re

    # 处理特殊标签 @cda-random：从 CDA 图中随机选一张
    if '@cda-random' in content:
        cda_images = ['4.png', '6.png', '7.jpg']
        chosen = random.choice(cda_images)
        print(f"\n  [@cda-random] 随机选中：{chosen}")
        cdn_url = resolve_image_ref(token, chosen)
        if cdn_url:
            content = content.replace('@cda-random', cdn_url)
            content = content.replace('![](@cda-random)', f'<img src="{cdn_url}" />')

    pattern = re.compile(r'@([\w.\\/:-]+\.(?:png|jpg|jpeg|gif|bmp))')
    matches = pattern.findall(content)
    if not matches:
        return content

    print(f"\n[图片处理] 发现 {len(matches)} 个图片引用")
    for ref in matches:
        cdn_url = resolve_image_ref(token, ref)
        if cdn_url:
            content = content.replace(f'@{ref}', cdn_url)
            content = content.replace(f'![](@{ref})', f'<img src="{cdn_url}" />')
            content = content.replace(f'![]({ref})', f'<img src="{cdn_url}" />')
            # 也支持 HTML 风格的 src="@1.png"
            content = content.replace(f'src="@{ref}"', f'src="{cdn_url}"')
            content = content.replace(f"src='@{ref}'", f"src='{cdn_url}'")
            print(f"  [替换] @{ref}")
    return content


def cmd_prepare():
    """
    预处理文章：将 Markdown 中的 @图片 替换为 CDN URL，输出 HTML
    用法：python wechat_publisher.py prepare <input.md> [output.html]

    如果未指定 output.html，则输出到 input（同名）.html
    """
    if len(sys.argv) < 3:
        print("用法：python wechat_publisher.py prepare <input.md> [output.html]")
        sys.exit(1)

    in_path = Path(sys.argv[2])
    if not in_path.exists():
        print(f"[错误] 文件不存在：{in_path}")
        sys.exit(1)

    # 检查是否已 compose：如果输入是 _raw.md，自动先 compose
    if in_path.stem.endswith('_raw'):
        composed_path = in_path.with_stem(in_path.stem.replace('_raw', '_composed'))
        print(f"  [检测] 输入为原始文件，先执行 compose")
        # 暂存 argv，模拟 compose 调用
        old_argv = sys.argv[:]
        sys.argv = ['wechat_publisher.py', 'compose', str(in_path)]
        cmd_compose()
        sys.argv = old_argv
        in_path = composed_path
        print(f"  [检测] 切换为合成文件：{in_path.name}")

    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else in_path.with_suffix('.html')

    content = in_path.read_text(encoding='utf-8')
    token = get_token()

    # 替换图片引用
    content = process_content_images(token, content)

    use_simple = '--simple' in sys.argv
    if use_simple:
        # 基础排版（宋体 + 标题层次）
        html_lines = [
            '<section style="font-family: SimSun, \'宋体\', serif; font-size: 15px; line-height: 2; color: #333; padding: 0 5px;">',
            '<style>',
            '  h1{font-size:24px;font-weight:normal;font-family:SimHei,\'黑体\',sans-serif;margin:20px 0 12px;line-height:1.5;color:#222}',
            '  h2{font-size:20px;font-weight:bold;margin:16px 0 10px;line-height:1.5;color:#333}',
            '  h3{font-size:18px;font-weight:bold;margin:12px 0 8px;line-height:1.5;color:#444}',
            '  h4{font-size:15px;font-weight:bold;margin:10px 0 6px;color:#555}',
            '  p{font-size:15px;margin:8px 0;line-height:2;font-family:SimSun,\'宋体\',serif}',
            '  img{max-width:100%;height:auto;display:block;margin:10px auto}',
            '</style>',
        ]
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('#'):
                level = min(len(line.split()[0]), 6)
                title = line.lstrip('#').strip()
                html_lines.append(f'<h{level}>{title}</h{level}>')
            elif line == '':
                pass
            elif line.startswith('http') and any(ext in line.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.qpic.cn', '.weixin.qq']):
                html_lines.append(f'<p style="text-align:center;margin:12px 0;"><img src="{line}" style="max-width:100%;border-radius:4px;" /></p>')
            elif line.startswith('<img'):
                html_lines.append(f'<p style="text-align:center;margin:12px 0;">{line}</p>')
            else:
                html_lines.append(f'<p>{line}</p>')
        html_lines.append('</section>')
        final_html = '\n'.join(html_lines)
    else:
        # 精美排版：调用 Node.js 渲染器（xiaonan0527 引擎，去除页脚）
        import subprocess, re as _re
        scripts_dir = Path(__file__).parent / 'scripts'
        render_script = scripts_dir / 'render.mjs'
        if not render_script.exists():
            print(f"[错误] 渲染脚本不存在：{render_script}")
            sys.exit(1)

        # 将 CDN URL 转为 Markdown 图片格式让渲染器识别
        content = _re.sub(r'(https?://[^\s]+(?:qpic|weixin)[^\s]*)', r'![](\1)', content)

        proc = subprocess.run(
            ['node', str(render_script)],
            input=content.encode('utf-8'),
            capture_output=True,
            timeout=30,
            cwd=str(scripts_dir)
        )
        if proc.returncode != 0:
            stderr = proc.stderr.decode('utf-8', errors='replace')
            print(f"[错误] 渲染失败：{stderr}")
            # 回退到基础排版
            print("[回退] 使用基础排版")
            cmd_prepare()
            return
        final_html = proc.stdout.decode('utf-8', errors='replace')
        print(f"  [排版] xiaonan0527 引擎，已去除页脚")

    # 写入结果
    out_path.write_text(final_html, encoding='utf-8')
    print(f"\n[OK] 已生成 HTML：{out_path}")
    print(f"      正文中包含 {len(IMG_PATTERN_CACHE)} 张已上传的微信 CDN 图片")


# 修改 cmd_draft 中的内容处理部分
def _load_and_process_content(token, art):
    """加载并处理一篇文章的内容和图片"""
    content = ''

    # 读取内容文件
    if 'content_file' in art and art['content_file']:
        cf_path = Path(art['content_file'])
        if cf_path.exists():
            content = cf_path.read_text(encoding='utf-8')
        else:
            print(f"  [警告] 内容文件不存在：{art['content_file']}")
            content = '<p></p>'
    elif 'content' in art:
        content = art['content']
    else:
        content = '<p></p>'

    # 处理正文中的 @图片 引用（仅当 content_file 是原始 Markdown 时）
    content = process_content_images(token, content)

    # 处理 images 列表（作为附录追加）
    for img_path in art.get('images', []):
        cdn_url = resolve_image_ref(token, img_path)
        if cdn_url:
            content += f'\n<p><img src="{cdn_url}" /></p>'

    return content


def cmd_help():
    print("""
微信公众号官方 API 发布工具（适配未认证订阅号）

可用命令：
  status                  查看草稿箱
  published               获取已发布文章链接
  upload <图片路径>        上传图片到微信 CDN，返回 URL
  compose <input.md>      自动合成：插入正文三图 + CDA 底部
  compose --no-footer <input.md>  合成时不加 CDA 尾缀（供插件同步用）
  add-footer <input.md>   给已合成的文件补回 CDA 尾缀
  prepare <input.md>      预处理 Markdown：上传 @图片 后输出 HTML
  draft <config.json>     根据配置创建草稿（自动替换 @图片）
  update-draft [media_id html1 html2]  更新已有草稿（补尾缀用）
  open                    用浏览器打开公众号草稿箱

完整工作流（单篇文章）：
  python wechat_publisher.py compose article.md
  python wechat_publisher.py prepare article.md
  python wechat_publisher.py open

图片引用方式：
  在文章正文中用 @1.png 引用项目根目录的图片
  脚本会自动上传到微信 CDN 并替换为可直接显示链接

  @1.png        → 项目根目录或配图7月/目录下的 1.png
  @配图7月/2.jpg  → 指定目录的图片
  @3..png       → 支持子目录和特殊文件名

配置文件示例 (draft)：
[
  {
    "title": "文章标题1",
    "content_file": "outputs/article1/content.html",
    "cover": "配图8月",        # 可以是目录，自动随机选一张
    "author": "作者"
  },
  {
    "title": "文章标题2",
    "content_file": "outputs/article2/content.html",
    "cover": "配图7月/xxx.jpg",  # 也可以是具体文件
    "author": "作者"
  }
]

快速开始：
  1. 用 Markdown 写好文章，图片用 @1.png 引用
  2. python wechat_publisher.py prepare article.md → 生成 HTML
  3. 创建 outputs/config.json
  4. python wechat_publisher.py draft outputs/config.json
  5. python wechat_publisher.py open  # 预览草稿
    """)


def cmd_published():
    """
    获取已发布的公众号文章链接
    用法：python wechat_publisher.py published
    """
    token = get_token()

    # 尝试 freepublish/batchget API
    try:
        url = f'{BASE_URL}/freepublish/batchget'
        resp = requests.post(url, params={'access_token': token},
            json={'offset': 0, 'count': 10, 'no_content': 0}, timeout=15)
        data = resp.json()

        if 'item' in data and data['item']:
            print(f"\n[已发布文章] 共 {data.get('total_count', 0)} 篇（最近10篇）")
            print("=" * 60)
            links = []
            for item in data['item']:
                for art in item.get('article_list', []):
                    title = art.get('title', '无标题')
                    url_link = art.get('url', '')
                    print(f"  {title}")
                    if url_link:
                        print(f"    {url_link}")
                        links.append(url_link)
                    for sub in art.get('articles', []):
                        sub_url = sub.get('url', '')
                        if sub_url:
                            print(f"       {sub_url}")
                            links.append(sub_url)
            return links
        elif 'errcode' in data and data['errcode'] == 48001:
            print("[提示] freepublish API 无权限，改用浏览器方式")
            return _fetch_links_via_browser()
        else:
            print(f"[提示] 未获取到已发布文章：{data}")
            return []
    except Exception as e:
        print(f"[错误] 获取已发布文章失败：{e}")
        return []




def _fetch_links_via_browser():
    """引导用户通过浏览器获取已发布文章链接"""
    print("""
请在浏览器中打开公众号后台「已发表」页面，然后用以下命令抓取:

  opencli browser wechat bind
  opencli browser wechat eval \"document.querySelectorAll('.appmsg').forEach(e=>{let t=e.querySelector('.weui-desktop-mass-appmsg__title')?.innerText.trim();let l=e.querySelector('a')?.href;if(l)console.log(t,l)})\"

或直接手动复制链接给我。
    """)
    return []


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        cmd_help()
        sys.exit(0)

    cmd = sys.argv[1]
    commands = {
        'status': cmd_status,
        'published': cmd_published,
        'upload': cmd_upload,
        'draft': cmd_draft,
        'prepare': cmd_prepare,
        'compose': cmd_compose,
        'add-footer': cmd_add_footer,
        'update-draft': cmd_update_draft,
        'open': cmd_open,
    }
    if cmd in commands:
        commands[cmd]()
    else:
        print(f"未知命令: {cmd}")
        cmd_help()
