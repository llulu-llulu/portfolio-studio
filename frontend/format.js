/** Display formatting only; no business valuation is computed here. */
export const $ = (selector) => document.querySelector(selector);
export const escape = (value) => String(value).replace(/[&<>"']/g, (s) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
export const money = (value) => Number(value).toLocaleString('zh-CN', {minimumFractionDigits:2, maximumFractionDigits:2});
export const integer = (value) => Number(value).toLocaleString('zh-CN');
export const date = (value) => new Intl.DateTimeFormat('zh-CN', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value));
export const colors = ['#177b65','#78a995','#bdcda9','#d6bd8c','#a8b7c3','#e4e8e2'];

export const threshold = (portfolio, type) =>
  (Number(portfolio.rules[type === 'industry' ? 'industry_threshold' : 'single_instrument_threshold']) * 100).toFixed(2);
