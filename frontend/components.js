import { escape, money, integer, colors, threshold } from './format.js';

export function heading(kicker, title, description, action='') {
  return `<div class="page-heading"><div><div class="eyebrow">${kicker}</div><h1>${escape(title)}</h1><p>${description}</p></div>${action}</div>`;
}

export function stats(portfolio, mode='original') {
  return `<section class="stats" aria-label="组合指标">
    <div class="stat primary"><div class="stat-label">总资产 <span>CNY</span></div><strong><small>¥</small>${money(portfolio.total_assets)}</strong><div class="stat-bottom"><span class="live-dot"></span>${mode === 'original' ? '持仓市值 + 现金余额' : '固定价格、零费用 · 总资产守恒'}</div></div>
    <div class="stat"><div class="stat-label">可用现金 <span>↗</span></div><strong><small>¥</small>${money(portfolio.cash)}</strong><div class="stat-bottom">占总资产 ${portfolio.cash_weight_pct}%</div></div>
    <div class="stat"><div class="stat-label">持仓市值 <span>▥</span></div><strong><small>¥</small>${money(portfolio.market_value)}</strong><div class="stat-bottom">持有 ${portfolio.holding_count} 个标的</div></div>
    <div class="stat"><div class="stat-label">集中度提醒 <span class="${portfolio.warnings.length ? 'amber' : 'green'}">◉</span></div><strong>${portfolio.warnings.length}<small class="unit">项</small></strong><div class="stat-bottom">${portfolio.warnings.length ? '查看下方超限对象与阈值' : '所有标的及行业均未超限'}</div></div>
  </section>`;
}

export function warningCards(portfolio) {
  if (!portfolio.warnings.length) return `<div class="all-clear"><span>✓</span><strong>集中度检查通过</strong><p>所有标的 ≤ ${threshold(portfolio, 'instrument')}%，所有行业 ≤ ${threshold(portfolio, 'industry')}%。等于阈值不触发提醒。</p></div>`;
  return `<div class="warning-list">${portfolio.warnings.map(w => `<div class="warning-card"><div class="warning-icon">!</div><div><div class="warning-title">${escape(w.name)}<span class="pill amber-pill">${w.type === 'industry' ? '行业集中' : '单一标的'}</span></div><div class="warning-value">${w.actual_pct}% <span>${w.actual_pct === w.threshold_pct ? '实际略高于' : '高于'} ${w.threshold_pct}% 阈值</span></div>${w.actual_pct === w.threshold_pct ? '<p class="rounding-note">显示值已舍入，提醒按未舍入比例判断。</p>' : ''}</div><div class="warning-status">超限</div></div>`).join('')}</div>`;
}

export function distribution(portfolio) {
  const segments = [...portfolio.industries.map(x=>({name:x.name,pct:Number(x.weight_pct)})),{name:'现金',pct:Number(portfolio.cash_weight_pct)}];
  let angle = 0;
  const stops = segments.map((x,i) => {const start=angle; angle+=x.pct; return `${colors[i % colors.length]} ${start}% ${angle}%`;});
  return `<div class="distribution"><div class="donut" style="background:conic-gradient(${stops.join(',')})" role="img" aria-label="行业与现金资产结构"><div><span>总资产</span><strong>${Number(portfolio.total_assets)/10000}<small>万元</small></strong><span>人民币 CNY</span></div></div><div class="legend">${segments.map((s,i)=>`<div><span class="legend-name"><i style="background:${colors[i % colors.length]}"></i>${escape(s.name)}</span><strong>${s.pct.toFixed(2)}%</strong></div>`).join('')}</div></div>`;
}

export function holdings(portfolio) {
  return `<div class="table-wrap"><table><thead><tr><th>标的名称 / 代码</th><th>行业</th><th class="num">价格（元）</th><th class="num">持仓数量</th><th class="num">市值（元）</th><th class="num">资产占比</th><th>集中度</th></tr></thead><tbody>${portfolio.positions.map(p=>`<tr><td><strong>${escape(p.name)}</strong><small class="sub">${escape(p.symbol)}</small></td><td><span class="sector">${escape(p.industry)}</span></td><td class="num muted">${money(p.price)}</td><td class="num">${integer(p.quantity)}</td><td class="num weight">${money(p.market_value)}</td><td class="num"><div class="weight-cell"><span>${p.weight_pct}%</span><div class="mini-track"><i class="${p.over_limit?'over':''}" style="width:${p.weight_pct}%"></i></div></div></td><td><span class="pill ${p.over_limit?'amber-pill':'neutral-pill'}">${p.over_limit?'超出阈值':'未超限'}</span></td></tr>`).join('')}</tbody></table></div>`;
}

export function comparison(current) {
  return `<section class="panel comparison"><div class="panel-header"><h2>调仓前后对比</h2><span class="small muted">原始 → 模拟 · 金额单位：元</span></div><div class="comparison-summary"><div><span>可用现金</span><strong>${money(current.before.cash)}<i>→</i>${money(current.after.cash)}</strong></div><div><span>集中度提醒</span><strong>${current.before.warnings.length}<i>→</i>${current.after.warnings.length}<small>项</small></strong></div><div><span>总资产</span><strong>${money(current.after.total_assets)}<span class="pill green-pill">保持不变</span></strong></div></div>
    <div class="table-wrap"><table><thead><tr><th>标的</th><th class="num">持仓数量</th><th class="num">市值</th><th class="num">资产占比</th><th>集中度</th></tr></thead><tbody>${current.after.positions.map((p,i)=>{const prev=current.before.positions[i];const changed=prev.quantity!==p.quantity; return `<tr class="${changed?'changed':''}"><td><strong>${escape(p.name)}</strong><small class="sub">${escape(p.symbol)}</small></td><td class="num">${prev.quantity}<span class="arrow">→</span><strong>${p.quantity}</strong></td><td class="num">${money(prev.market_value)}<span class="arrow">→</span><strong>${money(p.market_value)}</strong></td><td class="num">${prev.weight_pct}%<span class="arrow">→</span><strong>${p.weight_pct}%</strong></td><td><span class="pill ${p.over_limit?'amber-pill':'neutral-pill'}">${p.over_limit?'超出阈值':'未超限'}</span></td></tr>`;}).join('')}</tbody></table></div><div class="industry-compare"><h3>行业集中度</h3>${current.after.industries.map(s=>`<div><span>${escape(s.name)}</span><span>${current.before.industries.find(x=>x.name===s.name).weight_pct}% <span class="arrow">→</span> <strong>${s.weight_pct}%</strong></span><span class="pill ${s.over_limit?'amber-pill':'neutral-pill'}">${s.over_limit ? `超出 ${threshold(current.after, 'industry')}%` : '未超限'}</span></div>`).join('')}</div></section>`;
}

export function steps(current) {
  if (!current.steps.length) return '<div class="empty compact"><span>⇄</span><h3>从第一笔调整开始</h3><p>添加买卖操作，实时查看调仓后的结构。<br>原始组合始终保留。</p></div>';
  return `<ol class="steps">${current.steps.map(s=>`<li><span class="step-index">${s.index}</span><div><strong><span class="${s.side==='sell'?'green':'blue'}">${s.side==='sell'?'卖出':'买入'}</span> ${escape(current.before.positions.find(p=>p.symbol===s.symbol).name)}</strong><small>${s.symbol} · ${integer(s.quantity)} 股 × ¥${money(current.before.positions.find(p=>p.symbol===s.symbol).price)}</small></div><div class="step-money"><strong>${s.side==='sell'?'+':'−'}${money(s.amount)}</strong><small>余额 ${money(s.cash_after)}</small></div></li>`).join('')}</ol>`;
}

