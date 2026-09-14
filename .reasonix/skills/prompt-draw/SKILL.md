---
name: prompt-draw
description: 从选题池按分组抽题，生成两套完整提示词（含标题微调防重），也作为 article-push-workflow 的子步骤被调用
---

# prompt-draw

提示词抽取工具。当用户说 **"抽两套提示词出来"** 或类似指令时执行。

**注意：** 在日常推送流程中，此步骤已集成到 `article-push-workflow`（触发词"开始推送"），无需手动调用。本 skill 仅用于需要手动抽取提示词的场景。

## 执行流程

1. 运行 `python scripts/draw_prompts.py --save`
2. 脚本会自动将两套提示词保存到 `outputs/prompts_YYYYMMDD_HHMMSS.md`
3. 用记事本打开该文件供用户复制

### 辅助命令

- `python scripts/draw_prompts.py --list-unused` — 查看选题池中哪些选题还没写过，方便排期

## 选题规则

- 选题来源：`TOPIC_POOL` 常量（可直接替换为你自己的选题池）
- 每天两篇自动从**不同分组**各选1篇（6分组：选科分数/适合人群/专业对比/学习技能/就业发展/填报策略），确保主题差异
- 标题自动**微调**（加年份前缀、同义替换等）以避免百家号判重
- 系统记录已用题号，全部用完前不重复

## 维护说明

替换 `TOPIC_POOL` 即可自定义选题池，分组名可自由增删。
