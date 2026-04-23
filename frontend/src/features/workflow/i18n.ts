/**
 * 节点类型与类别的中文映射 — 前端侧，后端 manifest.name/category 保持英文稳定。
 * 未命中的 type 回退 manifest.name；未命中的 category 回退原字符串。
 */

export const NODE_TYPE_CN: Record<string, string> = {
  "start": "开始",
  "answer": "回答",
  "llm": "大模型",
  "if-else": "条件分支",
  "knowledge-retrieval": "知识检索",
  "iteration": "循环",
  "parameter-extractor": "参数提取",
  "question-classifier": "问题分类",
  "http-request": "HTTP 请求",
  "code": "代码",
  "template": "模板",
  "variable-aggregator": "变量聚合",
  "variable-splitter": "变量拆分",
  "builtin.echo": "回显",
  "human_approval": "人工审批",
}

export const CATEGORY_CN: Record<string, string> = {
  trigger: "触发",
  knowledge: "知识",
  llm: "大模型",
  agent: "智能体",
  logic: "逻辑",
  extension: "扩展",
  output: "输出",
  memory: "记忆",
}

export function nodeNameCn(type: string, fallback?: string): string {
  return NODE_TYPE_CN[type] ?? fallback ?? type
}

export function categoryCn(category: string): string {
  return CATEGORY_CN[category] ?? category
}
