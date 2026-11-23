import type { Condition, WidgetRule } from './types';

export function ruleCondition(rule: WidgetRule): Condition {
  return rule.condition ?? { kind: 'comparison', source: rule.source, path: rule.path, operator: rule.operator, value: rule.value };
}

export function conditionCount(node: Condition): number {
  return 1 + (node.kind === 'comparison' ? 0 : node.children.reduce((sum, child) => sum + conditionCount(child), 0));
}
