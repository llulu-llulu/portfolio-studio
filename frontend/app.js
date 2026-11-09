import { $, escape, money, date, threshold } from './format.js';
import { api } from './api.js';
import { heading, stats, warningCards, distribution, holdings, comparison, steps } from './components.js';
import { simulationMarkup } from './editor.js';

let base, result, operations = [], busy = false, routeSequence = 0, saveRequest = null;
let formState = {symbol:'A01', side:'sell', quantity:'100', name:''};
let errorText = '', saveError = '', toastTimer, savedSignature = null;

function contentSignature() {
  return JSON.stringify({name: formState.name.trim(), operations});
}

function hasUnsavedDraft() {
  return operations.length > 0 && contentSignature() !== savedSignature;
}

function snapshotBadge(portfolio) {
  $('.snapshot-badge').innerHTML = `<span class="live-dot"></span>固定快照 · ${date(portfolio.snapshot_at).split(' ')[0]}`;
}

function toast(message) {
  $('#toast').textContent = message; $('#toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 4500);
}

function overview() {
  snapshotBadge(base);
  $('#main').innerHTML = heading('PORTFOLIO OVERVIEW', '组合概览', '看清资产分布，让每一次调整都有依据。', '<a class="button primary-button" href="#simulate">开始调仓模拟 <span>↗</span></a>')+
    `<div class="context-line"><span class="pill neutral-pill">${escape(base.name)}</span><span>${escape(base.portfolio_id)}</span><span class="divider">|</span><span>行情快照 ${date(base.snapshot_at)}（北京时间）</span></div>`+
    stats(base)+`<div class="overview-grid"><section class="panel"><div class="panel-header"><h2>资产分布</h2><span class="muted small">按总资产占比</span></div>${distribution(base)}<div class="panel-foot">现金计入总资产，不归属任何行业。</div></section><section class="panel"><div class="panel-header"><h2>集中度检查</h2><span class="pill ${base.warnings.length ? 'amber-pill' : 'green-pill'}">${base.warnings.length} 项提醒</span></div>${warningCards(base)}<div class="rule-note">单一标的 &gt; ${threshold(base, 'instrument')}% · 行业 &gt; ${threshold(base, 'industry')}%<br>严格大于阈值时提醒，使用未舍入数值判断。</div></section></div>
    <section class="panel holdings"><div class="panel-header"><h2>持仓明细 <span class="count">${base.positions.length}</span></h2><span class="muted small">固定价格 · 原始组合</span></div>${holdings(base)}</section>`;
}

function captureForm() {
  if ($('#symbol')) formState = {symbol:$('#symbol').value,side:$('input[name="side"]:checked').value,quantity:$('#quantity').value,name:$('#plan-name').value};
}

function setBusy(value) {
  busy = value;
  document.querySelectorAll('#trade-form button, #trade-form input, #trade-form select, #save-form button, #save-form input, #reset').forEach(el=>{el.disabled=Boolean(value);});
  if ($('#trade-form button')) $('#trade-form button').innerHTML=value === 'simulation'?'正在校验…':'添加并计算 <span>＋</span>';
  if ($('#save-form button')) $('#save-form button').innerHTML=value === 'save'?'正在保存…':'保存方案 <span>↗</span>';
  if ($('#save-form button')) $('#save-form button').disabled=value || !operations.length;
  if ($('#reset')) $('#reset').disabled=value || !operations.length;
  document.querySelectorAll('#trade-form, #save-form').forEach(form => form.setAttribute('aria-busy', String(Boolean(value))));
}

function showError(message, area='trade') {
  if (area === 'save') saveError=message;
  else errorText=message;
  const el=$(area === 'save' ? '#save-error' : '#form-error');
  if (el) {el.hidden=false;el.textContent=message;el.focus();}
  else toast(message);
}

function simulationView() {
  result ||= {before:base, after:base, steps:[]};
  const current=result;
  snapshotBadge(base);
  $('#main').innerHTML=simulationMarkup(base, current, formState, {trade:errorText, save:saveError}, hasUnsavedDraft());
  const updateHint=()=>{const p=current.after.positions.find(x=>x.symbol===$('#symbol').value);$('#instrument-hint').textContent=`快照价格 ¥${money(p.price)} · 当前可卖 ${p.quantity} 股`;};
  $('#symbol').addEventListener('change',updateHint);updateHint();
  $('#trade-form').addEventListener('submit',addOperation);
  $('#save-form').addEventListener('submit',savePlan);
  $('#reset').addEventListener('click',()=>{if(busy)return;if(confirm('清空当前模拟的操作？原始组合和已保存方案不会改变。')){captureForm();operations=[];result=null;errorText='';saveError='';saveRequest=null;savedSignature=null;simulationView();}});
  $('#plan-name').addEventListener('input', () => {
    captureForm();
    $('#draft-status').textContent = hasUnsavedDraft() ? '有未保存的模拟，请保存后再刷新' : operations.length ? '当前模拟已保存' : '临时模拟在刷新后清空，保存方案可随时重开';
  });
  setBusy(busy);
}

async function addOperation(event) {
  event.preventDefault(); if(busy)return; captureForm();
  if(!/^[1-9]\d*$/.test(formState.quantity) || !Number.isSafeInteger(Number(formState.quantity)) || Number(formState.quantity)>1e9) {
    showError('数量必须是 1 至 1,000,000,000 的正整数；不能为零、负数或小数。');return;
  }
  const candidate=[...operations,{symbol:formState.symbol,side:formState.side,quantity:Number(formState.quantity)}];
  setBusy('simulation');
  try {
    const calculated=await api('/simulations',{snapshot_id:base.snapshot_id,operations:candidate});
    operations=candidate;result=calculated;errorText='';saveError='';saveRequest=null;
    if(location.hash==='#simulate') simulationView();
    toast(`第 ${operations.length} 笔操作已计算，总资产保持不变`);
  }catch(error){showError(error.message);}
  finally{
    setBusy(false);
    if (!errorText && $('#quantity')) $('#quantity').focus({preventScroll:true});
  }
}

async function savePlan(event) {
  event.preventDefault();if(busy||!operations.length)return;captureForm();
  if(!formState.name.trim()){showError('请为方案填写非空名称', 'save');return;}
  const signature=contentSignature();
  const initiatingRoute=routeSequence;
  if(saveRequest?.signature!==signature)saveRequest={signature,id:crypto.randomUUID()};
  setBusy('save');
  try{
    const plan=await api('/plans',{snapshot_id:base.snapshot_id,name:formState.name.trim(),operations,request_id:saveRequest.id});
    savedSignature=signature;
    saveError='';toast('方案已保存，可在已保存方案中重新查看');
    if (initiatingRoute === routeSequence && location.hash === '#simulate') location.hash=`#plan/${plan.id}`;
    else if (location.hash === '#simulate') simulationView();
  }catch(error){showError(error.message, 'save');}
  finally{setBusy(false);}
}

async function plansView(sequence) {
  const data=await api('/plans');if(sequence!==routeSequence)return;
  $('#main').innerHTML=heading('SAVED SCENARIOS','已保存方案','保留每一次模拟，随时回到当时的调整思路。','<a class="button primary-button" href="#simulate">进入模拟工作台 <span>↗</span></a>')+
    (data.plans.length?`<div class="plans-grid">${data.plans.map(p=>`<a class="panel plan-card" href="#plan/${p.id}"><div class="plan-card-top"><span class="plan-icon">▤</span><span class="pill neutral-pill">只读方案</span></div><h2>${escape(p.name)}</h2><p>${p.operation_count} 笔交易 · ${escape(p.snapshot_id)}</p><div class="plan-card-bottom"><small>${date(p.created_at)}（北京）</small><span>查看方案 ↗</span></div></a>`).join('')}</div>`:'<section class="panel empty"><span>▤</span><h2>还没有保存的方案</h2><p>在模拟工作台添加交易并命名保存，方案会出现在这里。</p><a class="button primary-button" href="#simulate">创建第一个方案 ↗</a></section>');
}

async function detailView(id, sequence) {
  const plan=await api(`/plans/${encodeURIComponent(id)}`);if(sequence!==routeSequence)return;
  snapshotBadge(plan.result.before);
  $('#main').innerHTML=heading('SAVED SCENARIO',plan.name,`保存于 ${date(plan.created_at)}（北京时间） · ${plan.operations.length} 笔交易`,'<a href="#plans" class="button secondary-button">← 返回方案列表</a>')+
    `<div class="saved-banner"><span>✓</span><div><strong>已保存 · 只读查看</strong><p>绑定快照 ${escape(plan.result.before.snapshot_id)} · ${date(plan.result.before.snapshot_at)}（北京时间）。原始组合未改变。</p></div></div>`+
    stats(plan.result.after,'simulated')+`<div class="detail-grid"><section class="panel"><div class="panel-header"><h2>已保存操作</h2><span class="small muted">按顺序执行</span></div>${steps(plan.result)}</section><section class="panel"><div class="panel-header"><h2>模拟后集中度</h2></div>${warningCards(plan.result.after)}</section></div>`+comparison(plan.result);
}

async function route() {
  captureForm();const sequence=++routeSequence;
  const hash=location.hash || '#overview';
  const key=hash.startsWith('#plan/')?'plans':hash.slice(1);
  document.querySelectorAll('[data-nav]').forEach(a=>{a.classList.toggle('active',a.dataset.nav===key);if(a.dataset.nav===key)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  $('#breadcrumb-current').textContent=({overview:'组合概览',simulate:'调仓模拟',plans:'已保存方案'})[key] || '页面';
  $('#main').innerHTML='<div class="loading" role="status"><span class="spinner"></span>正在读取数据…</div>';
  try{
    if(!base){
      const loaded=await api('/portfolio');
      if(sequence!==routeSequence)return;
      base=loaded;
    }
    if(sequence!==routeSequence)return;
    if(hash==='#overview')overview();
    else if(hash==='#simulate')simulationView();
    else if(hash==='#plans')await plansView(sequence);
    else if(hash.startsWith('#plan/'))await detailView(hash.slice(6),sequence);
    else{location.hash='#overview';return;}
    if(sequence === routeSequence){
      $('#main').focus({preventScroll:true});
      window.scrollTo(0,0);
    }
  }catch(error){if(sequence!==routeSequence)return;$('#main').innerHTML=`<section class="panel empty"><span>!</span><h1>暂时无法打开</h1><p role="alert">${escape(error.message)}</p><button id="retry" class="button primary-button">重新加载</button><a class="button secondary-button" href="#overview">返回组合概览</a></section>`;$('#retry').addEventListener('click',route);}
}

window.addEventListener('hashchange',route);
window.addEventListener('beforeunload',event=>{
  captureForm();
  if(hasUnsavedDraft()){event.preventDefault();event.returnValue='';}
});
if(!location.hash)history.replaceState(null,'','#overview');
route();
