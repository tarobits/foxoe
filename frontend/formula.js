import { readPath } from './model.js';

// Deliberately small arithmetic language. Never evaluate JavaScript or property access.
export function parseFormula(expression) {
  if (typeof expression !== 'string' || expression.length > 512) throw new Error('invalidFormula');
  const tokens = expression.match(/\s+|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|"(?:[^"\\\n\r]|\\["\\/bfnrt]|\\u[\da-fA-F]{4})*"|[A-Za-z_][A-Za-z_0-9]*|[()+\-*/%,]/g) || [];
  if (tokens.join('') !== expression) throw new Error('invalidFormula');
  const input = tokens.filter(token => token.trim());
  if (input.length > 128) throw new Error('invalidFormula');
  let position = 0;
  const take = token => { if (input[position++] !== token) throw new Error('invalidFormula'); };
  function atom(depth) {
    if (depth > 16) throw new Error('invalidFormula');
    const token = input[position++];
    if (token === '+' || token === '-') return { op: 'unary', sign: token, child: atom(depth + 1) };
    if (token === '(') { const node = expressionAt(0, depth + 1); take(')'); return node; }
    if (token === 'value') return { op: 'value' };
    if (token && /^(?:\d|\.)/.test(token) && Number.isFinite(Number(token))) return { op: 'number', value: Number(token) };
    if (!['field','abs','round','floor','ceil','min','max'].includes(token)) throw new Error('invalidFormula');
    take('(');
    if (token === 'field') {
      const raw = input[position++];
      if (!raw?.startsWith('"')) throw new Error('invalidFormula');
      const path = JSON.parse(raw);
      if (!validFieldPath(path)) throw new Error('invalidFormula');
      take(')'); return { op: 'field', path };
    }
    const args = [expressionAt(0, depth + 1)];
    while (input[position] === ',') { position++; args.push(expressionAt(0, depth + 1)); }
    take(')');
    if (args.length > 8 || (['abs','floor','ceil'].includes(token) && args.length !== 1) || (token === 'round' && args.length > 2)) throw new Error('invalidFormula');
    return { op: token, args };
  }
  function expressionAt(priority, depth) {
    let left = atom(depth);
    const priorities = { '+': 1, '-': 1, '*': 2, '/': 2, '%': 2 };
    while ((priorities[input[position]] || 0) > priority) {
      const op = input[position++];
      left = { op, left, right: expressionAt(priorities[op], depth + 1) };
    }
    return left;
  }
  const tree = expressionAt(0, 0);
  if (position !== input.length) throw new Error('invalidFormula');
  function checkDepth(node, depth = 0) {
    if (depth > 16) throw new Error('invalidFormula');
    for (const child of [...(node.args || []), node.left, node.right, node.child].filter(Boolean)) checkDepth(child, depth + 1);
  }
  checkDepth(tree);
  return tree;
}

export function validFieldPath(path) {
  if (typeof path !== 'string' || path.length > 200) return false;
  const normalized = path.replace(/^\$\.?/, '').replace(/\[(\d+)\]/g, '.$1');
  return /^[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*$/.test(normalized) && !normalized.split('.').some(key => ['__proto__','constructor','prototype'].includes(key));
}

export function evaluateFormula(expression, selected, data) {
  try {
    const numeric = value => { if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error('formulaDataUnavailable'); return value; };
    function run(node) {
      if (node.op === 'number') return node.value;
      if (node.op === 'value') return numeric(selected);
      if (node.op === 'field') return numeric(readPath(data, node.path));
      if (node.op === 'unary') return (node.sign === '-' ? -1 : 1) * run(node.child);
      let result;
      if (node.args) {
        const args = node.args.map(run);
        if (node.op === 'round') {
          const digits = args[1] ?? 0;
          if (!Number.isInteger(digits) || digits < 0 || digits > 10) throw new Error('formulaDecimals');
          const factor = 10 ** digits;
          result = Math.round(args[0] * factor) / factor;
        } else result = Math[node.op](...args);
      } else {
        const a = run(node.left), b = run(node.right);
        if ((node.op === '/' || node.op === '%') && b === 0) throw new Error('formulaDivisionByZero');
        result = node.op === '+' ? a + b : node.op === '-' ? a - b : node.op === '*' ? a * b : node.op === '/' ? a / b : a % b;
      }
      if (!Number.isFinite(result)) throw new Error('formulaNonFinite');
      return result;
    }
    return { value: run(parseFormula(expression)), error: null };
  } catch (error) { return { value: null, error: ['formulaDataUnavailable','formulaDivisionByZero','formulaNonFinite','formulaDecimals'].includes(error.message) ? error.message : 'invalidFormula' }; }
}
