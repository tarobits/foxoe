import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseFormula, evaluateFormula } from '../frontend/formula.js';
import { formatValue } from '../frontend/model.js';
const cases=JSON.parse(readFileSync(new URL('./formula-cases.json',import.meta.url)));

test('arithmetic grammar accepts bounded expressions and rejects executable or malformed input',()=>{
  for(const formula of cases.valid) assert.doesNotThrow(()=>parseFormula(formula),formula);
  for(const formula of [...cases.invalid,'('.repeat(18)+'1'+')'.repeat(18),'1+'.repeat(70)+'1','1'.repeat(513)]) assert.throws(()=>parseFormula(formula),formula);
});
test('formulas combine numeric JSON fields without changing source data, and recover from errors',()=>{
  const data={total:5000,used:1068.77,items:[{mm:4}]}, original=structuredClone(data);
  assert.ok(Math.abs(evaluateFormula('(field("total") - field("used")) / 1000',null,data).value-3.93123)<1e-12);
  assert.equal(evaluateFormula('2 + 3 * 4 - 10 / 2',0,data).value,9);
  assert.equal(evaluateFormula('round(value / 1000, 2)',3931.23,data).value,3.93);
  assert.equal(evaluateFormula('field("items[0].mm")',null,data).value,4);
  for(const value of [null,undefined,true,'4',{},Infinity]) assert.equal(evaluateFormula('value + 1',value,data).error,'formulaDataUnavailable');
  assert.equal(evaluateFormula('value / 0',4,data).error,'formulaDivisionByZero');
  assert.equal(evaluateFormula('value % 0',4,data).error,'formulaDivisionByZero');
  assert.equal(evaluateFormula('value * 1e308',4,data).error,'formulaNonFinite');
  assert.equal(evaluateFormula('round(value,-1)',4,data).error,'formulaDecimals');
  assert.equal(evaluateFormula('field("missing")',0,data).error,'formulaDataUnavailable');
  assert.equal(evaluateFormula('value / 2',4,data).value,2);
  assert.deepEqual(data,original);
  assert.equal(formatValue(3.9,'en',3),'3.900');assert.equal(formatValue(3.9,'de',0),'4');
});
