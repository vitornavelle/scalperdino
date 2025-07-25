async function fetchStatus() {
  const statusEl = document.getElementById('service-status');
  const btnEl = document.getElementById('toggle-btn');

  let isPaused = false;
  let isOffline = false;

  try {
    // Consulta o status local do robô para detectar "pausado"
    const stateRes = await fetch('/api/state', {cache: "no-store"});
    const state = await stateRes.json();
    isPaused = !!state.paused;

    // Consulta o status real da Bitget
    const realRes = await fetch('/api/real_status', {cache: "no-store"});
    const realData = await realRes.json();

    // Atualiza badge de status
    if (isPaused) {
      statusEl.textContent = 'PAUSADO';
      statusEl.className = 'badge badge-pausado';
      btnEl.textContent = 'Retomar Robô';
      btnEl.className = 'badge badge-pausado';
    } else if (realData.status && realData.status.includes('Em posição')) {
      statusEl.textContent = realData.status + ' (ATIVO)';
      statusEl.className = 'badge badge-ativo';
      btnEl.textContent = 'Pausar Robô';
      btnEl.className = 'badge badge-ativo';
    } else if (realData.status && realData.status.includes('Sem posição aberta')) {
      statusEl.textContent = 'ATIVO';
      statusEl.className = 'badge badge-ativo';
      btnEl.textContent = 'Pausar Robô';
      btnEl.className = 'badge badge-ativo';
    } else {
      statusEl.textContent = 'ATIVO';
      statusEl.className = 'badge badge-ativo';
      btnEl.textContent = 'Pausar Robô';
      btnEl.className = 'badge badge-ativo';
    }
  } catch (e) {
    // Erro na API: OFFLINE
    statusEl.textContent = 'OFFLINE';
    statusEl.className = 'badge badge-offline';
    btnEl.textContent = 'Serviço OFFLINE';
    btnEl.className = 'badge badge-offline';
    isOffline = true;
  }

  // Bloqueia o botão se offline
  btnEl.disabled = isOffline;
}

async function fetchLogs() {
  const res = await fetch('/api/logs');
  const lines = await res.json();
  // Inverte o array para mostrar o mais recente primeiro
  const desc = lines.slice().reverse();
  document.getElementById('log-area').textContent = desc.join('\n');
}

async function fetchMetrics() {
  const res = await fetch('/api/metrics');
  const m = await res.json();
  document.getElementById('pnl-day').textContent = m.pnl_day.toFixed(2);
  document.getElementById('pnl-7d').textContent = m.pnl_7d.toFixed(2);
  document.getElementById('pnl-15d').textContent = m.pnl_15d.toFixed(2);
  document.getElementById('pnl-30d').textContent = m.pnl_30d.toFixed(2);
}

async function loadConfig() {
  console.log('loadConfig() chamado');
  const res = await fetch('/api/config');
  const cfg = await res.json();
  const form = document.getElementById('config-form');

  for (let key in cfg) {
    if (key === 'tpPortions') {
      cfg[key].forEach((val, idx) => {
        const inp = form.querySelector('input[name="tpPortions.' + idx + '"]');
        if (inp) inp.value = val;
      });
    } else {
      const input = form.querySelector('input[name="' + key + '"]');
      if (input) input.value = cfg[key];
    }
  }
}

document.getElementById('config-form').addEventListener('submit', async function(e) {
  e.preventDefault();
  const raw = new FormData(e.target);
  const data = {};
  raw.forEach(function(v, k) {
    if (k.indexOf('tpPortions.') === 0) {
      const idx = parseInt(k.split('.')[1], 10);
      data.tpPortions = data.tpPortions || [];
      data.tpPortions[idx] = parseFloat(v);
    } else {
      data[k] = isNaN(v) ? v : parseFloat(v);
    }
  });
  await fetch('/api/config', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
  toastr.success('Configurações salvas!');
});

document.getElementById('toggle-btn').addEventListener('click', async function() {
  const btnEl = document.getElementById('toggle-btn');
  if (btnEl.disabled) return;
  const res = await fetch('/api/toggle', { method: 'POST' });
  const result = await res.json();
  fetchStatus();
  toastr.info(result.paused ? 'Robô PAUSADO' : 'Robô RETOMADO');
});

window.onload = function() {
  fetchStatus();
  fetchLogs();
  fetchMetrics();
  loadConfig();
  setInterval(function() {
    fetchStatus();
    fetchLogs();
    fetchMetrics();
  }, 5000);
};
