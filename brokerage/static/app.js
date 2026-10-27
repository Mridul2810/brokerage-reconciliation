const byId = (id) => document.getElementById(id);
let loadVersion = 0;
let selectedRun = null;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

async function request(path) {
  const response = await fetch(path);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`);
  }
  return response.json();
}

function message(text, error = false) {
  byId('message').textContent = text;
  byId('message').className = error ? 'error' : '';
}

function money(value) {
  // Keep server decimal text exact; format only the integer part for display.
  const [whole, cents = '00'] = value.split('.');
  return `$${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${cents}`;
}

function date(value) {
  return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

async function showReport(runId, version) {
  selectedRun = runId;
  const panel = byId('report-detail');
  panel.hidden = true;
  message(`Loading run ${runId}…`);
  try {
    const report = await request(`/reconciliation/runs/${runId}`);
    if (version !== loadVersion || selectedRun !== runId) return;
    byId('report-title').textContent = `Run ${report.run_id} · ${report.breaks.length ? 'Break evidence' : 'Matching comparison'}`;
    byId('report-source').textContent = `${report.clearing_source} · Created ${date(report.created_at)}`;
    byId('report-result').textContent = report.breaks.length ? `${report.breaks.length} ORIGINAL BREAK${report.breaks.length === 1 ? '' : 'S'}` : 'MATCH';
    byId('report-result').className = `chip ${report.breaks.length ? 'warn' : 'good'}`;
    const container = byId('breaks');
    container.replaceChildren();
    if (!report.breaks.length) container.append(element('p', 'All supplied execution records matched at comparison time.', 'empty'));
    for (const item of report.breaks) {
      const card = element('article', undefined, 'break-card');
      const heading = element('div', undefined, 'break-heading');
      heading.append(element('h3', `${item.reference} · ${item.field}`), element('span', item.status.toUpperCase(), `chip ${item.status === 'resolved' ? 'good' : 'warn'}`));
      card.append(heading, element('p', `${item.kind.replaceAll('_', ' ')} · Break #${item.break_id}`));
      const values = element('div', undefined, 'break-values');
      for (const [label, value] of [['Internal record', item.internal_value], ['Clearing record', item.clearing_value]]) {
        const block = element('div');
        block.append(element('small', label), element('strong', value));
        values.append(block);
      }
      card.append(values);
      const timeline = element('div', undefined, 'timeline');
      if (!item.history.length) timeline.append(element('p', 'No investigation events recorded. Status defaults to open.'));
      for (const event of item.history) {
        const row = element('div', undefined, 'event');
        const head = element('header');
        head.append(element('strong', event.actor), element('span', event.status, 'chip'));
        const time = element('time', date(event.created_at));
        time.dateTime = event.created_at;
        head.append(time);
        row.append(head, element('p', event.note));
        timeline.append(row);
      }
      card.append(timeline);
      container.append(card);
    }
    byId('snapshots').replaceChildren(element('h3', 'Internal records'), element('pre', JSON.stringify(report.internal_records, null, 2)), element('h3', 'Clearing records'), element('pre', JSON.stringify(report.clearing_records, null, 2)));
    byId('fingerprint').textContent = `Parsed clearing records SHA-256: ${report.clearing_records_sha256}`;
    panel.hidden = false;
    message('Live balances loaded. Report evidence is preserved from its comparison run.');
  } catch (error) {
    if (version === loadVersion && selectedRun === runId) message(error.message, true);
  }
}

async function loadAccount(event) {
  if (event) event.preventDefault();
  const version = ++loadVersion;
  selectedRun = null;
  const account = byId('account').value.trim();
  byId('refresh').disabled = true;
  byId('report-detail').hidden = true;
  byId('runs').replaceChildren();
  byId('runs-empty').hidden = false;
  byId('runs-empty').textContent = 'Loading reports…';
  byId('positions').replaceChildren();
  for (const id of ['available', 'reserved', 'total']) byId(id).textContent = '—';
  message('Loading account from PostgreSQL…');
  try {
    const encoded = encodeURIComponent(account);
    const [summary, runs] = await Promise.all([request(`/accounts/${encoded}/summary`), request(`/reconciliation/runs?account=${encoded}`)]);
    if (version !== loadVersion) return;
    byId('available').textContent = money(summary.available_usd);
    byId('reserved').textContent = money(summary.reserved_usd);
    byId('total').textContent = money(summary.total_cash_usd);
    if (!summary.positions.length) byId('positions').append(element('p', 'No share positions for this account.', 'empty'));
    for (const position of summary.positions) {
      const block = element('div', undefined, 'position');
      block.append(element('strong', position.symbol), element('span', `${position.quantity} shares`), element('small', position.status));
      byId('positions').append(block);
    }
    byId('runs-empty').hidden = runs.length > 0;
    byId('runs-empty').textContent = 'No reconciliation runs saved for this account.';
    for (const run of runs) {
      const row = element('tr');
      row.append(element('td', `#${run.run_id}`), element('td', run.clearing_source), element('td', date(run.created_at)), element('td', String(run.break_count)));
      const state = element('td');
      state.append(element('span', run.break_count === 0 ? 'MATCH' : run.unresolved_count === 0 ? 'ALL RESOLVED' : `${run.unresolved_count} UNRESOLVED`, `chip ${run.unresolved_count === 0 ? 'good' : 'warn'}`));
      const action = element('td');
      const button = element('button', 'View evidence →');
      button.type = 'button';
      button.setAttribute('aria-label', `View evidence for run ${run.run_id}`);
      button.addEventListener('click', () => showReport(run.run_id, version));
      action.append(button);
      row.append(state, action);
      byId('runs').append(row);
    }
    message('Account loaded. Select a reconciliation run to inspect its evidence.');
    if (runs.length) await showReport(runs.find((run) => run.break_count > 0)?.run_id ?? runs[0].run_id, version);
  } catch (error) {
    if (version === loadVersion) {
      byId('runs-empty').textContent = 'Unable to load account data.';
      message(error.message, true);
    }
  } finally {
    if (version === loadVersion) byId('refresh').disabled = false;
  }
}

byId('account-form').addEventListener('submit', loadAccount);
loadAccount();
