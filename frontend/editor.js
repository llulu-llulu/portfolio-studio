import { escape, date } from './format.js';
import { heading, warningCards, comparison, steps } from './components.js';

/** Pure editor markup; event handling and accepted state live in app.js. */
export function simulationMarkup(base, current, form, errors, dirty) {
  return heading('REBALANCE LAB', '调仓模拟', '按顺序添加交易，在同一份行情快照下比较结果。',
      '<span class="pill green-pill">原始组合保持独立</span>') + `
    <div class="context-line">
      <span>行情快照 ${date(base.snapshot_at)}（北京时间）</span>
      <span id="draft-status">${dirty ? '有未保存的模拟，请保存后再刷新' : current.steps.length ? '当前模拟已保存' : '临时模拟在刷新后清空，保存方案可随时重开'}</span>
    </div>
    <div class="sim-layout">
      <aside class="sim-editor">
        <section class="panel">
          <div class="panel-header"><h2>添加操作</h2><span class="small muted">${current.steps.length} / 100</span></div>
          <form id="trade-form" novalidate>
            <fieldset class="side-toggle">
              <legend class="sr-only">交易方向</legend>
              <label><input type="radio" name="side" value="sell" ${form.side === 'sell' ? 'checked' : ''}><span>卖出</span></label>
              <label><input type="radio" name="side" value="buy" ${form.side === 'buy' ? 'checked' : ''}><span>买入</span></label>
            </fieldset>
            <label class="field-label" for="symbol">交易标的</label>
            <select id="symbol">${base.positions.map(p => `
              <option value="${p.symbol}" ${form.symbol === p.symbol ? 'selected' : ''}>${p.symbol} · ${escape(p.name)}</option>`).join('')}
            </select>
            <div id="instrument-hint" class="input-hint"></div>
            <label class="field-label" for="quantity">交易数量 <span>股</span></label>
            <input id="quantity" type="text" inputmode="numeric" autocomplete="off"
              value="${escape(form.quantity)}" aria-describedby="quantity-help form-error">
            <p id="quantity-help" class="input-hint">输入正整数，不要求整手交易。</p>
            <button class="button primary-button full" type="submit">添加并计算 <span>＋</span></button>
          </form>
          <div id="form-error" class="form-error" role="alert" tabindex="-1" ${errors.trade ? '' : 'hidden'}>${escape(errors.trade)}</div>
        </section>
        <section class="panel save-panel">
          <h2>保存这次调整</h2><p>给方案一个名称，稍后随时重新查看。</p>
          <form id="save-form" novalidate>
            <label class="field-label" for="plan-name">方案名称</label>
            <input id="plan-name" type="text" maxlength="60" value="${escape(form.name)}"
              placeholder="例如：降低科技集中度" aria-describedby="save-error" required>
            <button type="submit" class="button secondary-button full" ${!current.steps.length ? 'disabled' : ''}>保存方案 <span>↗</span></button>
          </form>
          <div id="save-error" class="form-error" role="alert" tabindex="-1" ${errors.save ? '' : 'hidden'}>${escape(errors.save)}</div>
          <small>保存后只读 · 不影响原始组合</small>
        </section>
      </aside>
      <div class="sim-results">
        <section class="panel">
          <div class="panel-header"><h2>操作序列 <span class="count">${current.steps.length}</span></h2>
            <button class="text-button" id="reset" ${!current.steps.length ? 'disabled' : ''}>清空重来</button>
          </div>
          ${steps(current)}
        </section>
        <div class="sim-warning">${warningCards(current.after)}</div>
        ${comparison(current)}
      </div>
    </div>`;
}
