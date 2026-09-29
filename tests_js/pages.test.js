const test = require('node:test');
const assert = require('node:assert/strict');
function page(path) {
  let definition;
  global.Page = x => { definition = x; };
  delete require.cache[require.resolve(path)]; require(path);
  const instance = { data: JSON.parse(JSON.stringify(definition.data)) };
  instance.setData = patch => {
    for (const [key, value] of Object.entries(patch)) {
      const parts = key.split('.'); let target = instance.data;
      for (const part of parts.slice(0,-1)) target = target[part];
      target[parts[parts.length-1]] = value;
    }
  };
  for (const [key, value] of Object.entries(definition)) if (typeof value === 'function') instance[key] = value.bind(instance);
  instance.onLoad(); return instance;
}
const connection={baseUrl:'https://class.example',studentId:'s001',token:'parent-test-long-token'};
const cfg={grade:1,semester:1,unit:0,duration_minutes:10,chinese_help:true,difficulty:'basic'};
test('configuration page loads actual values and only toasts after save', async()=>{
  const calls=[]; const toasts=[];
  global.wx={getStorageSync:()=>connection,showToast:t=>toasts.push(t),request:o=>{
    calls.push(o);
    if (o.url.includes('/api/words')) o.success({statusCode:200,data:{words:[{word:'apple'}],units:[{value:0,label:'整个学期'}]}});
    else o.success({statusCode:200,data:o.method==='PUT'?o.data:cfg});
  }};
  const p=page('../miniprogram/pages/english-config/index.js');
  await p.loadSaved(); assert.equal(p.data.ready,true);assert.equal(p.data.wordPreview,'apple');
  p.onDifficulty({detail:{value:'2'}}); await p.onSave();
  assert.equal(calls.find(x=>x.method==='PUT').data.difficulty,'challenge');assert.equal(toasts.length,1);
});
test('grade picker covers grades 1-12 and maps high school index to grade 12', async()=>{
  const calls=[];
  global.wx={getStorageSync:()=>connection,showToast:()=>{},request:o=>{calls.push(o);o.success({statusCode:200,data:{words:[{word:'announce'}],units:[{value:0,label:'整个学期'}]}})}};
  const p=page('../miniprogram/pages/english-config/index.js');
  assert.equal(p.data.grades.length,12);assert.equal(p.data.grades[11],'高三');
  await p.onGrade({detail:{value:'11'}});
  assert.equal(p.data.form.grade,12);assert.match(calls[0].url,/grade=12(&|$)/);
});
test('own LLM key goes only to server, is cleared from page, and failures are shown', async()=>{
  const calls=[];const stored=[];const toasts=[];let fail=false;
  global.wx={getStorageSync:()=>connection,setStorageSync:(k,v)=>stored.push(v),showToast:t=>toasts.push(t),request:o=>{
    calls.push(o);
    if (fail) { o.success({statusCode:422,data:{detail:'测试调用失败，未保存：自带模型的密钥无效或无权限'}}); return }
    o.success({statusCode:200,data:{mode:'custom',base_url:'https://api.example.com',model:'m1',key_hint:'sk-…9876',last_status:'ok'}});
  }};
  const p=page('../miniprogram/pages/english-config/index.js');
  p.onLlmInput({currentTarget:{dataset:{field:'base_url'}},detail:{value:'https://api.example.com'}});
  p.onLlmInput({currentTarget:{dataset:{field:'model'}},detail:{value:'m1'}});
  p.onLlmInput({currentTarget:{dataset:{field:'api_key'}},detail:{value:'sk-secret-9876'}});
  await p.onSaveLlm();
  const put=calls.find(x=>x.method==='PUT');assert.equal(put.data.api_key,'sk-secret-9876');assert.match(put.url,/\/api\/llm/);
  assert.equal(p.data.llmForm.api_key,'');assert.equal(p.data.llm.mode,'custom');assert.equal(toasts.length,1);
  assert.ok(!JSON.stringify(stored).includes('sk-secret'));
  fail=true;p.onLlmInput({currentTarget:{dataset:{field:'api_key'}},detail:{value:'bad'}});await p.onSaveLlm();
  assert.match(p.data.llmError,/未保存/);assert.equal(toasts.length,1);assert.equal(p.data.llmBusy,false);
});
test('failed configuration save never shows success', async()=>{
  const toasts=[];
  global.wx={getStorageSync:()=>connection,showToast:t=>toasts.push(t),request:o=>o.success({statusCode:503,data:{detail:'保存失败'}})};
  const p=page('../miniprogram/pages/english-config/index.js');p.data.ready=true;
  await p.onSave();assert.equal(p.data.error,'保存失败');assert.deepEqual(toasts,[]);assert.equal(p.data.saving,false);
});
test('result page separates request failure from empty successful history', async()=>{
  let status=503;
  global.wx={stopPullDownRefresh:()=>{},getStorageSync:()=>connection,request:o=>o.success({statusCode:status,data:status===200?{today:'2026-09-29',words:[]}:{detail:'连接失败'}})};
  const p=page('../miniprogram/pages/english-result/index.js');
  await p.refresh();assert.equal(p.data.loaded,false);assert.equal(p.data.error,'连接失败');
  status=200;await p.refresh();assert.equal(p.data.loaded,true);assert.equal(p.data.error,'');assert.deepEqual(p.data.todayWords,[]);
});
