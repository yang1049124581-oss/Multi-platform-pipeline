---
name: article-push-workflow
description: 全自动推送管线：从105题池抽词→生成文章→审核修复→排版（两套版本），零人工干预
---

# article-push-workflow

全自动推送管线。用户说 **"开始推送"、"做今天的推送"、"开始今天的推送工作"、"开始推文"** 时触发。

**核心原则：全程零请示。每一步自动执行，失败自动修复，通过自动进入下一步。**

---

## 执行流程

### Step 1：抽提示词

```bash
cd .
python scripts/draw_prompts.py --save
```

> ⚠️ **选题机制**：`draw_prompts.py` 从运营方指定的 **105题池**中按**6个分组**（选科分数/适合人群/专业对比/学习技能/就业发展/填报策略）**不同分组各选1篇**，确保每天两篇主题差异大。标题自动做微调（加年份前缀、同义替换等）以避免百家号判重。
>
> ⚠️ **防重机制**：脚本自动扫描 `outputs/*_raw.md` 中已有标题，避免推送相同标题文章；同时记录已选题号，105题全部用完前不重复。无需手动干预。

读取最新保存的 `outputs/prompts_YYYYMMDD_HHMMSS.md`，提取两套文章的：
- 主题类别（6大分组）
- 选题编号（#001~#105）
- 原标题（运营方指定）
- 微调后标题（实际发布用）
- 行文模板（T1-T5）
- CDA目标次数（4-7次）
- CDA融入位置（按模板的段落分布）
- 话术参考（行业背景型/能力建设型/岗位就业型/成长路径型）

### Step 2：生成文章（AI 执行）

根据 Step 1 提取的参数，按提示词的完整结构分别写出两篇文章。

**必须严格遵守的规则：**
- 标题不能出现 CDA
- CDA 不能出现在第一段
- CDA 不能出现在结尾总结段
- CDA 首次出现在第 3-5 段之间
- **全文CDA 4-7次**，分散在不同段落，禁止集中
- **不能有独立的「证书规划」章节**——CDA素材自然融入各段落
- 无表格、无小圆点、无AI痕迹词
- 营销词（必须/一定/唯一/最好/强烈推荐/推荐/报名/课程/培训/购买/咨询）每篇不超过2次
- 能力建设部分是全文最大篇幅
- 尾缀已加上：> 【扫码"CDA认证"小程序】...

**保存规则：**
- 文件名 = `outputs/{场景简称}_{方向简称}_raw.md`
- 场景简称取前4个字

### Step 3：审核 + 修复循环（核心）

对每篇文章：

```bash
python scripts/audit_article.py outputs/{文件名}_raw.md
```

**如果输出 `PASS（≥ 90 分）`** → 该篇通过，进入下一步。

**如果输出 `改（< 90 分）`** → 输出问题清单，进入修复循环：

   ```json
   {"date":"YYYY-MM-DD","article":"{文件名}","round":1,"issues":["..."],"fix_applied":"...","result":"PASS/改"}
   ```

**5 轮仍未 PASS** → 输出修复日志给用户，停止该文章的流程，等待人工介入。

### Step 4：排版（产出两套版本，分两批进草稿箱）

两篇全部 PASS 后执行。每篇文章必须产出**两个版本**——带尾缀版（公众号推送用）和无尾缀版（其他平台用），**都在草稿箱中各有一批草稿**。

**⚠️ 尾缀定义（重要）：**
- 尾缀 = 仅"扫码了解CDA数据分析师认证……"文字 + @8.jpg（二维码图）
- @cda-random（随机4/6/7.jpg）是**正文内容图**，不是尾缀，footer版和pure版都含有，不可删除

**⚠️ 使用 [output.md] 参数指定不同文件名，避免互相覆盖。**

```bash
# ============================================================
# 第1步：compose 带尾缀版（产出 *_footer.md）
# ============================================================
python wechat_publisher.py compose outputs/{文件名1}_raw.md outputs/{文件名1}_footer.md
python wechat_publisher.py compose outputs/{文件名2}_raw.md outputs/{文件名2}_footer.md

# ============================================================
# 第2步：compose 无尾缀纯净版（产出 *_pure.md）
# ============================================================
python wechat_publisher.py compose --no-footer outputs/{文件名1}_raw.md outputs/{文件名1}_pure.md
python wechat_publisher.py compose --no-footer outputs/{文件名2}_raw.md outputs/{文件名2}_pure.md

# ============================================================
# 第3步：prepare 生成HTML（上传图片到微信CDN）
# ============================================================
python wechat_publisher.py prepare outputs/{文件名1}_footer.md
python wechat_publisher.py prepare outputs/{文件名2}_footer.md
python wechat_publisher.py prepare outputs/{文件名1}_pure.md
python wechat_publisher.py prepare outputs/{文件名2}_pure.md

# ============================================================
# 第4步：draft 第1批——带尾缀版（公众号推送用）
# ============================================================
# 写入配置文件 outputs/draft_footer.json
# [{"title":"完整标题1","content_file":"outputs/{文件名1}_footer.html","cover":"配图8月","author":"账号A"},
#  {"title":"完整标题2","content_file":"outputs/{文件名2}_footer.html","cover":"配图8月","author":"账号A"}]
python wechat_publisher.py draft outputs/draft_footer.json

# ============================================================
# 第5步：draft 第2批——无尾缀版（其他平台用，也进草稿箱）
# ============================================================
# 写入配置文件 outputs/draft_pure.json
# [{"title":"完整标题1","content_file":"outputs/{文件名1}_pure.html","cover":"配图8月","author":"账号A"},
#  {"title":"完整标题2","content_file":"outputs/{文件名2}_pure.html","cover":"配图8月","author":"账号A"}]
python wechat_publisher.py draft outputs/draft_pure.json

# ============================================================
# 第6步：打开草稿箱确认
# ============================================================
python wechat_publisher.py open
```

产出文件：

| 文件 | 内容 | 用途 |
|------|------|------|
| `{文件}_footer.html` | 带尾缀+二维码 | 公众号推送（第1批草稿） |
| `{文件}_pure.html` | 无尾缀 | 其他平台（第2批草稿） |
| 公众号草稿1 | 带尾缀+正文三图 | 草稿箱第1批 |
| 公众号草稿2 | 无尾缀+正文三图 | 草稿箱第2批 |

### Step 5：自动链接采集

用户确认所有平台发布完成后：

```bash
python scripts/cdp_collect.py --titles "标题1,标题2"
```

### Step 6：汇报

```
✅ 今日推送已完成
━━━━━━━━━━━━━━━━━━
文章1: {标题} → {分数}分 PASS
文章2: {标题} → {分数}分 PASS
排版: 公众号草稿已创建，纯净版HTML已生成
━━━━━━━━━━━━━━━━━━
公众号草稿：已创建（带尾缀版已上传至微信服务器）
纯净版HTML：outputs/{文件}_composed.html（无尾缀，供其他平台使用）
各平台发布完成后跟我说"整理链接"，我来汇总链接。
```

---

## 修复优先级

执行修复时严格按照此顺序（致命问题优先）：

1. 标题公司视角（R012）- 可能 -20
2. 能力建设缺失（R010）- REJECT 级别
3. CDA ≥ 8 次（R002）- REJECT 级别
4. 独立证书模块/集中堆砌（R014）- -15
5. 培训导向（R013）- -50
6. CDA 位置错误（R003/R004）- -15
7. 结构缺失（R010）- -20/-10
8. 营销词超标（R006）- -5/次
9. CDA 次数不足 ≤2（R001）- -12
10. AI 痕迹词（R007）- -5
11. 话术重复（R005）- -5
12. 小圆点/表格（R008/R009）- -5/-20

---

## 文件

| 文件 | 用途 |
|------|------|
| `文章自动修复规则库.md` | 修复步骤标准库 |
| `state/fix_history.json` | 修复历史记录（供学习积累） |
| `scripts/draw_prompts.py` | 提示词抽取（105题池+分组选题+标题微调防重） |
| `scripts/audit_article.py` | 文章审核 |
| `wechat_publisher.py` | 排版发布（compose/prepare/draft/open/add-footer） |
| `scripts/strip_wechat_footer.py` | 清理CDA尾缀（备选） |

---

## 异常处理

### WeChat API 40164（IP 不在白名单）

`{"errcode": 40164, "errmsg": "invalid ip x.x.x.x, not in whitelist"}`

**原因：** 请求出口 IP 与公众号后台配置的 IP 白名单不一致。使用代理/VPN 时出口 IP 会随节点变化，建议把 `api.weixin.qq.com` 配置为直连。

**修复步骤：**

1. 报错信息中的 IP 即当前公网出口 IP
2. 到公众号后台 → 设置与开发 → 基本配置 → IP白名单，添加该 IP
3. IP 变化时按报错中出现的新 IP 追加即可

4. **验证修复：**
   ```bash
   python -c "import requests; r=requests.get('https://api.weixin.qq.com/cgi-bin/token', params={'grant_type':'client_credential','appid':'test','secret':'test'}, timeout=10); print(r.status_code, r.text[:100])"
   ```
   返回 `40013 invalid appid` 说明连接正常（appid 故意传错的）
