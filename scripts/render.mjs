#!/usr/bin/env node
/**
 * WeChat 排版渲染器（综合版）
 * 
 * 从 stdin 读取 Markdown（图片已替换为 CDN URL），输出微信兼容 HTML
 * 基于 xiaonan0527/wechat-publisher 渲染引擎，去除页脚尾巴
 * 
 * 用法：cat article.md | node render.mjs > article.html
 *       cat article.md | node render.mjs --theme magazine > article.html
 */

import { readFileSync } from 'fs';
import { markdownToSections } from './markdown-to-sections.mjs';
import { wxRenderSections } from './wechat-renderer.mjs';

// 读取 stdin
const input = readFileSync(0, 'utf-8');

// 解析参数
const theme = process.argv.includes('--theme') 
  ? process.argv[process.argv.indexOf('--theme') + 1] 
  : 'default';

// 去除页脚：传入空 footerSubtext
const options = {
  theme,
  footerSubtext: '',    // 去掉 ""
};

// 渲染
const sections = markdownToSections(input, options);
// 去掉最后一个 section（footer），因为 footerSubtext='' 仍会生成空 footer
const cleanSections = sections.filter(s => s.type !== 'footer');
const html = wxRenderSections(cleanSections, options);

console.log(html);
