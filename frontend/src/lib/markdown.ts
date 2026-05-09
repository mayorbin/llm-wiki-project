// frontend/src/lib/markdown.ts
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

const md = new MarkdownIt({
  html: false,        // 禁用 raw HTML（防 XSS）
  linkify: true,
  breaks: true,
  typographer: false, // 中文内容禁用智能引号
})

/**
 * 渲染 Markdown 内容为安全 HTML
 * - 预处理 [[PageName]] 和 [[PageName|text]] 为安全链接
 * - 通过 DOMPurify 清洗 HTML，防止 XSS 攻击
 */
export function renderMarkdown(raw: string, projectId: string): string {
  // 预处理 [[PageName]] → 安全链接
  const withLinks = raw
    .replace(/\[\[([^\]|]+)\]\]/g, (_, page: string) =>
      `[${page.trim()}](/${projectId}/pages/${encodeURIComponent(page.trim())})`)
    .replace(/\[\[([^\]]+)\|([^\]]+)\]\]/g, (_, page: string, text: string) =>
      `[${text.trim()}](/${projectId}/pages/${encodeURIComponent(page.trim())})`)

  // markdown → HTML
  const html = md.render(withLinks)

  // DOMPurify 清洗（标签/属性/URI 三层白名单）
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      'h1','h2','h3','h4','h5','h6','p','br','hr',
      'ul','ol','li','blockquote','pre','code',
      'strong','em','s','del','ins','mark',
      'a','img','table','thead','tbody','tr','th','td',
      'span','div',
    ],
    ALLOWED_ATTR: ['href','target','rel','src','alt','title','class','id'],
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|ftp):|[^a-z]|[a-z+.-]+(?:[^a-z+.-:]|$))/i,
  })
}
