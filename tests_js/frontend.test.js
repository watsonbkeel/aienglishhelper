const test = require('node:test');
const assert = require('node:assert/strict');
const base = '../miniprogram/utils/';
test('progress 0 practiced is not never practiced', () => {
  const v=require(base+'english-view.js');
  assert.equal(v.statusText({status:0,last_practiced_date:'2026-09-29'}),'继续练习');
  assert.equal(v.statusText({status:0}),'没练过');
});
test('today filter and cumulative labels', () => {
  const v=require(base+'english-view.js');
  const result=v.buildReport({today:'2026-09-29',words:[
    {word_id:'a',status:2,last_practiced_date:'2026-09-29',unclear_count:1},
    {word_id:'b',status:1,last_practiced_date:'2026-09-28',unclear_count:3}]});
  assert.equal(result.todayWords.length,1);
  assert.equal(result.todayWords[0].stateText,'会说了');
  assert.equal(result.todayWords[0].unclearText,'系统累计没听清 1 次');
  assert.equal(result.speakingCount,1);
});
test('connection refuses provider placeholders and mismatched base', () => {
  const v=require(base+'english-view.js');
  assert.throws(()=>v.validateConnection({baseUrl:'http://example.com',studentId:'s001',token:'abc'}));
  assert.doesNotThrow(()=>v.validateConnection({baseUrl:'https://class.example',studentId:'s001',token:'parent-token-very-long'}));
});
test('request failure is rejected, not empty report', async () => {
  global.wx={getStorageSync:()=>({baseUrl:'https://class.example',studentId:'s001',token:'parent-token-very-long'}),request:opts=>opts.success({statusCode:503,data:{detail:'未连接'}})};
  const api=require(base+'english-api.js');
  await assert.rejects(()=>api.progress(),/未连接/);
});
test('request adds student id and credential header', async () => {
  let observed;
  global.wx={getStorageSync:()=>({baseUrl:'https://class.example',studentId:'s001',token:'parent-token-very-long'}),request:opts=>{observed=opts;opts.success({statusCode:200,data:{today:'2026-09-29',words:[]}})}};
  const api=require(base+'english-api.js');await api.progress();
  assert.match(observed.url,/student_id=s001/);
  assert.equal(observed.header.Authorization,'Bearer parent-token-very-long');
  assert.doesNotMatch(observed.url,/parent-token/);
});
