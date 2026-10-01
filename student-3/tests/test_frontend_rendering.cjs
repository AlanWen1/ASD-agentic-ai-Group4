// Execute the real UI response handlers with a minimal DOM, without npm dependencies.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const code = fs.readFileSync(path.join(__dirname, '../frontend/static/app.js'), 'utf8');
const attack = '<img src=x onerror=alert(1)>';
function environment(payload, failed = false) {
  const elements = {'#mcpResult': {textContent: '', innerHTML: ''}, '#ragInput': {value: 'pay schedule'}, '#ragAnswer': {innerHTML: ''}};
  const context = vm.createContext({Intl, URL, console, window: {},
    localStorage: {getItem: () => 'test-token'},
    document: {querySelector: (id) => elements[id], addEventListener: () => {},
      createElement: () => ({textContent: '', get innerHTML() {
        return this.textContent.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      }})},
    fetch: async () => ({ok: !failed, status: failed ? 502 : 200, json: async () => payload}),
  });
  vm.runInContext(code, context);
  return {context, elements};
}
test('MCP income names render as text', async () => {
  const {context, elements} = environment({result: {items: [{source_name: attack, standard_amount: 10, payment_frequency: 'monthly'}]}});
  await vm.runInContext("callMcpQuery('get_income_sources')", context);
  assert.ok(elements['#mcpResult'].textContent.includes(attack));
  assert.equal(elements['#mcpResult'].innerHTML, '');
});
test('RAG answers and citation names are escaped while confidence remains visible', async () => {
  const {context, elements} = environment({answer: attack, citations: [attack], confidence_category: 'medium'});
  context.event = {preventDefault() {}};
  await vm.runInContext('sendRagQuestion(event)', context);
  const output = elements['#ragAnswer'].innerHTML;
  assert.ok(!output.includes('<img'));
  assert.ok(output.includes('&lt;img'));
  assert.ok(output.includes('medium') && output.includes('Sources:'));
});
test('RAG dependency errors are escaped', async () => {
  const {context, elements} = environment({error: attack}, true);
  context.event = {preventDefault() {}};
  await vm.runInContext('sendRagQuestion(event)', context);
  assert.ok(!elements['#ragAnswer'].innerHTML.includes('<img'));
  assert.ok(elements['#ragAnswer'].innerHTML.includes('&lt;img'));
});
