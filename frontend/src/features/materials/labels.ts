import type { Locator, MaterialFile } from './types'
export const statusLabel: Record<string,string> = {
  queued: '等待处理', processing: '正在解析', ready: '已完成', needs_review: '需核对识别范围',
  failed: '未完成', analyzing: '正在分析资料', needs_attention: '需确认重试', linked: '已用于需求确认', editing: '资料编辑中',
}
export function fileStatusText(file: Pick<MaterialFile, 'status' | 'included' | 'text_only_accepted'>) {
  if (!file.included) return '未纳入本次范围'
  if (file.status === 'needs_review' && file.text_only_accepted) return '已确认，仅采用文字'
  return statusLabel[file.status] || file.status
}
export const issueLabel: Record<string,string> = {
  ocr_required: '该页没有可提取文字，需要 OCR', page_visual_review_pending: '原页中的公式、图表尚未识别',
  page_text_extraction_failed: '该页文字提取失败', outline_limit_exceeded: '文件原生目录过长', outline_unreadable: '原生目录无法读取',
  formula_conversion_pending: '原生公式已保留，尚未转换为可用表达式', figure_or_chart_review_pending: '图片或图表尚未解读',
  complex_table_review_pending: '复杂表格中的合并单元格或嵌套内容需核对', dynamic_field_not_evaluated: '动态字段未执行',
  tracked_changes_require_decision: '文档包含未确认的修订记录', unsupported_word_body_element: '存在暂不支持的 Word 正文结构',
  secondary_word_parts_not_indexed: '页眉、页脚、脚注或批注暂未纳入', chart_data_review_pending: '图表数据尚未解读',
  no_readable_content: '未找到可用文字', image_description_pending: '图片已保存，图像识别尚待接入',
}
export function locationText(loc: Locator | null) {
  if (!loc) return '整个文件'
  if (loc.page) return `原文件第 ${loc.page} 页`
  if (loc.paragraph) return `Word 第 ${loc.paragraph} 段`
  if (loc.table) return `Word 第 ${loc.table} 张表`
  return '原图片'
}
