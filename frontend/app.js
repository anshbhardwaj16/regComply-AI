const API = '';

let analysisData = null;

// ── File input helpers ────────────────────────────────────────────────────────

document.getElementById('reg-file').addEventListener('change', e => {
  document.getElementById('reg-filename').textContent = e.target.files[0]?.name || 'No file chosen';
});
document.getElementById('ctl-file').addEventListener('change', e => {
  document.getElementById('ctl-filename').textContent = e.target.files[0]?.name || 'No file chosen';
});

function updateFileName(inputId, labelId) {
  const f = document.getElementById(inputId).files[0];
  document.getElementById(labelId).textContent = f?.name || 'No file chosen';
}

// ── Mode switcher ─────────────────────────────────────────────────────────────

function switchMode(mode) {
  document.getElementById('mode-compliance-view').classList.toggle('hidden', mode !== 'compliance');
  document.getElementById('mode-change-view').classList.toggle('hidden', mode !== 'change');
  document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
  document.getElementById(`mode-${mode}`).classList.add('active');
}

// ── Section / Tab helpers ─────────────────────────────────────────────────────

function showSection(id) {
  ['upload-section', 'loading-section', 'results-section'].forEach(s => {
    document.getElementById(s).classList.add('hidden');
  });
  document.getElementById(id).classList.remove('hidden');
}

function showTab(name, btn) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  if (btn) btn.classList.add('active');
  document.getElementById(`tab-${name}`).classList.add('active');
}

// ── Pipeline step helpers ─────────────────────────────────────────────────────

const STEP_ORDER = ['ingest', 'obligations', 'controls', 'mapping', 'gaps', 'remediation'];

function setStep(stepId, state, detail = '') {
  const el = document.getElementById(`step-${stepId}`);
  if (!el) return;
  const statusEl = el.querySelector('.step-status');
  const detailEl = document.getElementById(`detail-${stepId}`);
  el.className = `pipeline-step ${state}`;
  statusEl.className = `step-status ${state}`;
  statusEl.textContent = state === 'active' ? 'Running...' : state === 'done' ? '✓ Done' : 'Pending';
  if (detailEl && detail) detailEl.textContent = detail;
}

function setNextStepActive(doneStep) {
  const idx = STEP_ORDER.indexOf(doneStep);
  if (idx >= 0 && idx < STEP_ORDER.length - 1) {
    setStep(STEP_ORDER[idx + 1], 'active');
  }
}

function resetSteps() {
  STEP_ORDER.forEach(s => setStep(s, 'pending'));
  document.querySelectorAll('.step-detail').forEach(d => d.textContent = '');
}

function setLoadingMsg(msg) {
  document.getElementById('loading-msg').textContent = msg;
}

// ── Main analysis (SSE streaming) ─────────────────────────────────────────────

async function runAnalysis() {
  const regFile = document.getElementById('reg-file').files[0];
  const ctlFile = document.getElementById('ctl-file').files[0];
  const regText = document.getElementById('reg-text').value.trim();
  const ctlText = document.getElementById('ctl-text').value.trim();
  const regName = document.getElementById('reg-name').value;
  const bankName = document.getElementById('bank-name').value;

  if (!regFile && !regText) { alert('Please provide a regulation document or text.'); return; }
  if (!ctlFile && !ctlText) { alert('Please provide a control policy document or text.'); return; }

  showSection('loading-section');
  resetSteps();
  setStep('ingest', 'active');
  setLoadingMsg('Initializing agentic pipeline...');

  const formData = new FormData();
  if (regFile) formData.append('regulation_file', regFile);
  else formData.append('regulation_text', regText);
  if (ctlFile) formData.append('control_file', ctlFile);
  else formData.append('control_text', ctlText);
  formData.append('regulation_name', regName);
  formData.append('bank_name', bankName);

  try {
    // Try streaming endpoint first; fall back to regular endpoint if server hasn't reloaded yet
    const probeResp = await fetch(`${API}/health`);
    const health = probeResp.ok ? await probeResp.json() : {};
    const useStream = health.version === '2.0.0';

    if (useStream) {
      await runWithStreaming(formData);
    } else {
      await runWithFallback(formData);
    }
  } catch (err) {
    alert('Analysis failed: ' + err.message);
    showSection('upload-section');
  }
}

async function runWithStreaming(formData) {
  const resp = await fetch(`${API}/api/analyze-stream`, { method: 'POST', body: formData });
  if (!resp.ok) throw new Error(await resp.text());

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop();

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      let payload;
      try { payload = JSON.parse(line.slice(6)); } catch { continue; }

      if (payload.event === 'step') {
        const stepName = payload.step === 'ingestion' ? 'ingest' : payload.step;
        setStep(stepName, 'done', payload.msg || '');
        setNextStepActive(stepName);
        setLoadingMsg(payload.msg || '');
      } else if (payload.event === 'complete') {
        STEP_ORDER.forEach(s => setStep(s, 'done'));
        setLoadingMsg('Analysis complete!');
        analysisData = payload.result;
        renderResults(payload.result);
        showSection('results-section');
      } else if (payload.event === 'error') {
        throw new Error(payload.message);
      }
    }
  }
}

async function runWithFallback(formData) {
  // Animate steps manually while waiting for the single response
  setStep('ingest', 'done', 'Documents ingested');
  setStep('obligations', 'active');
  setLoadingMsg('Extracting regulatory obligations...');

  // Try /api/analyze (file upload) first, else /api/analyze-text (JSON)
  const regText = formData.get('regulation_text');
  const ctlText = formData.get('control_text');
  let result;

  if (regText && ctlText) {
    // Text-only path
    const resp = await fetch(`${API}/api/analyze-text`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        regulation_text: regText,
        control_text: ctlText,
        regulation_name: formData.get('regulation_name'),
        bank_name: formData.get('bank_name'),
      }),
    });
    if (!resp.ok) throw new Error(await resp.text());
    result = await resp.json();
  } else {
    const resp = await fetch(`${API}/api/analyze`, { method: 'POST', body: formData });
    if (!resp.ok) throw new Error(await resp.text());
    result = await resp.json();
  }

  // Animate remaining steps
  ['obligations','controls','mapping','gaps','remediation'].forEach(s => {
    setStep(s, 'done');
  });
  setLoadingMsg('Analysis complete!');
  analysisData = result;
  renderResults(result);
  showSection('results-section');
}

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

function resetAnalysis() {
  analysisData = null;
  showSection('upload-section');
}

// ── Render results ────────────────────────────────────────────────────────────

function renderResults(data) {
  document.getElementById('results-title').textContent = `${data.bank_name} — ${data.regulation_name}`;
  document.getElementById('exec-summary').textContent = data.executive_summary;

  // Score gauge
  const score = data.compliance_score;
  document.getElementById('gauge-value').textContent = score + '%';
  document.getElementById('gauge-value').className = 'gauge-value ' +
    (score >= 70 ? 'green' : score >= 40 ? 'orange' : 'red');
  const circumference = 326.7;
  const offset = circumference - (score / 100) * circumference;
  const fill = document.getElementById('gauge-fill');
  fill.style.strokeDashoffset = offset;
  fill.style.stroke = score >= 70 ? '#43a047' : score >= 40 ? '#fb8c00' : '#e53935';

  document.getElementById('score-full').textContent = data.fully_covered;
  document.getElementById('score-partial').textContent = data.partially_covered;
  document.getElementById('score-none').textContent = data.not_covered;
  document.getElementById('score-total').textContent = data.total_obligations;
  document.getElementById('score-controls').textContent = data.controls.length;

  const oblMap = Object.fromEntries(data.obligations.map(o => [o.id, o]));
  const ctlMap = Object.fromEntries(data.controls.map(c => [c.id, c]));
  const gapMap = Object.fromEntries(data.gaps.map(g => [g.obligation_id, g]));
  const remMap = Object.fromEntries(data.remediations.map(r => [r.gap_id, r]));
  const mappingMap = Object.fromEntries(data.mappings.map(m => [m.obligation_id, m]));

  renderTraceability(data, oblMap, ctlMap, gapMap, remMap, mappingMap);
  renderGaps(data.gaps);
  renderRemediations(data.remediations, gapMap);
  renderControls(data.controls);
  renderObligations(data.obligations, mappingMap);
}

function renderTraceability(data, oblMap, ctlMap, gapMap, remMap, mappingMap) {
  const container = document.getElementById('traceability-list');
  container.innerHTML = '';

  data.obligations.forEach(obl => {
    const mapping = mappingMap[obl.id] || {};
    const coverage = mapping.coverage || 'None';
    const covClass = coverage === 'Full' ? 'full' : coverage === 'Partial' ? 'partial' : 'none';
    const gap = gapMap[obl.id];
    const rem = gap ? remMap[gap.id] : null;
    const ctl = mapping.control_id ? ctlMap[mapping.control_id] : null;

    const card = document.createElement('div');
    card.className = `trace-card ${covClass}`;
    card.innerHTML = `
      <div class="trace-header" onclick="toggleTrace(this)">
        <span class="trace-obl-id">${obl.id}</span>
        <span class="trace-obl-text">${obl.text.substring(0, 110)}${obl.text.length > 110 ? '…' : ''}</span>
        <span class="trace-badge badge-${covClass}">${coverage}</span>
        <span class="trace-expand">▼</span>
      </div>
      <div class="trace-body">
        <div class="trace-chain">
          <div class="chain-item">
            <span class="chain-label">📋 Regulation</span>
            <span class="chain-value">${obl.regulation_ref || data.regulation_name}</span>
          </div>
          <div class="chain-item">
            <span class="chain-label">📌 Obligation</span>
            <span class="chain-value">${obl.text}</span>
          </div>
          <div class="chain-item">
            <span class="chain-label">🏷️ Category</span>
            <span class="chain-value">${obl.category} · Applies to: ${obl.applicability}</span>
          </div>
          <div class="chain-item">
            <span class="chain-label">🛡️ Control</span>
            <span class="chain-value">${ctl ? `<strong>${ctl.id}</strong>: ${ctl.text}` : '<em style="color:var(--danger)">No matching control found</em>'}</span>
          </div>
          <div class="chain-item">
            <span class="chain-label">📊 Coverage</span>
            <span class="chain-value"><span class="trace-badge badge-${covClass}">${coverage}</span>${mapping.confidence !== undefined ? ` · Confidence: ${Math.round(mapping.confidence * 100)}%` : ''}</span>
          </div>
          ${gap ? `
          <div class="chain-item">
            <span class="chain-label">⚠️ Gap</span>
            <span class="chain-value"><span class="risk-badge risk-${gap.risk_level}">${gap.risk_level}</span> · Score: ${gap.risk_score}/100 · ${gap.reasoning}</span>
          </div>` : ''}
          ${rem ? `
          <div class="chain-item">
            <span class="chain-label">💊 Remediation</span>
            <span class="chain-value">${rem.action} <em>(${rem.timeline} · Owner: ${rem.owner})</em></span>
          </div>` : (!gap ? `
          <div class="chain-item">
            <span class="chain-label">✅ Status</span>
            <span class="chain-value" style="color:var(--success);font-weight:600">Fully covered — no gaps identified.</span>
          </div>` : '')}
        </div>
      </div>`;
    container.appendChild(card);
  });
}

function toggleTrace(header) {
  const body = header.nextElementSibling;
  const arrow = header.querySelector('.trace-expand');
  body.classList.toggle('open');
  arrow.textContent = body.classList.contains('open') ? '▲' : '▼';
}

function renderGaps(gaps) {
  const container = document.getElementById('gaps-list');
  container.innerHTML = '';
  if (!gaps.length) {
    container.innerHTML = '<p style="color:var(--success);font-weight:600;padding:1rem">🎉 No compliance gaps identified!</p>';
    return;
  }
  gaps.forEach(gap => {
    const div = document.createElement('div');
    div.className = `gap-card ${gap.risk_level}`;
    div.innerHTML = `
      <div class="gap-header">
        <span class="gap-id">${gap.id}</span>
        <span class="risk-badge risk-${gap.risk_level}">${gap.risk_level}</span>
        <span style="font-size:0.78rem;color:var(--text-muted);flex:1">${gap.regulation_ref || ''}</span>
        <span class="gap-score">Risk Score: ${gap.risk_score}/100</span>
      </div>
      <div class="gap-text">${gap.obligation_text}</div>
      <div class="gap-reasoning">⚠️ ${gap.reasoning}</div>
      <div class="gap-coverage">Coverage: <strong>${gap.coverage}</strong></div>`;
    container.appendChild(div);
  });
}

function renderRemediations(remediations, gapMap) {
  const container = document.getElementById('remediation-list');
  container.innerHTML = '';
  if (!remediations.length) {
    container.innerHTML = '<p style="color:var(--success);font-weight:600;padding:1rem">✅ No remediations needed.</p>';
    return;
  }
  remediations.forEach(rem => {
    const gap = gapMap[rem.gap_id] || {};
    const effortColor = rem.effort === 'Very High' || rem.effort === 'High' ? 'var(--danger)' :
                        rem.effort === 'Medium' ? 'var(--warning)' : 'var(--success)';
    const div = document.createElement('div');
    div.className = 'rem-card';
    div.innerHTML = `
      <div class="rem-header">
        <div class="rem-priority">${rem.priority}</div>
        <span class="rem-gap-id">${rem.gap_id}</span>
        ${gap.risk_level ? `<span class="risk-badge risk-${gap.risk_level}">${gap.risk_level}</span>` : ''}
      </div>
      <div class="rem-action">${rem.action}</div>
      <div class="rem-meta">
        <span class="rem-tag">👤 ${rem.owner}</span>
        <span class="rem-tag">⏱️ ${rem.timeline}</span>
        <span class="rem-tag" style="color:${effortColor}">💪 Effort: ${rem.effort}</span>
      </div>`;
    container.appendChild(div);
  });
}

function renderControls(controls) {
  const container = document.getElementById('controls-list');
  container.innerHTML = '';
  controls.forEach(ctl => {
    const score = ctl.effectiveness_score ?? '--';
    const rating = ctl.effectiveness_rating ?? 'Unknown';
    const ratingColor = rating === 'Strong' ? 'var(--success)' :
                        rating === 'Adequate' ? 'var(--accent)' :
                        rating === 'Weak' ? 'var(--warning)' : 'var(--danger)';
    const div = document.createElement('div');
    div.className = 'ctl-card';
    div.innerHTML = `
      <div class="ctl-header">
        <span class="item-id">${ctl.id}</span>
        <span class="item-ref">${ctl.policy_ref || ''}</span>
        <span class="cat-tag">${ctl.category}</span>
        <span class="ctl-type-tag">${ctl.control_type || ''}</span>
        <span class="ctl-auto-tag">${ctl.automation_level || ''}</span>
      </div>
      <div class="item-text">${ctl.text}</div>
      <div class="ctl-effectiveness">
        <div class="eff-bar-wrap">
          <div class="eff-bar" style="width:${score}%;background:${ratingColor}"></div>
        </div>
        <span class="eff-score" style="color:${ratingColor}">${score}/100</span>
        <span class="eff-rating" style="color:${ratingColor};font-weight:600">${rating}</span>
      </div>
      <div class="item-meta">Owner: ${ctl.owner}</div>`;
    container.appendChild(div);
  });
}

function renderObligations(obligations, mappingMap) {
  const container = document.getElementById('obligations-list');
  container.innerHTML = '';
  obligations.forEach(obl => {
    const m = mappingMap[obl.id] || {};
    const cov = m.coverage || 'None';
    const bc = cov === 'Full' ? 'badge-full' : cov === 'Partial' ? 'badge-partial' : 'badge-none';
    const div = document.createElement('div');
    div.className = 'item-card';
    div.innerHTML = `
      <div class="item-header">
        <span class="item-id">${obl.id}</span>
        <span class="item-ref">${obl.regulation_ref || ''}</span>
        <span class="cat-tag">${obl.category}</span>
        <span class="trace-badge ${bc}">${cov}</span>
      </div>
      <div class="item-text">${obl.text}</div>
      <div class="item-meta">Applies to: ${obl.applicability}</div>`;
    container.appendChild(div);
  });
}

// ── Export ────────────────────────────────────────────────────────────────────

function exportReport() {
  if (!analysisData) return;
  const blob = new Blob([JSON.stringify(analysisData, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `regcomply-report-${Date.now()}.json`;
  a.click();
}

// ── What-if Simulator ─────────────────────────────────────────────────────────

function openSimulator() {
  document.getElementById('sim-modal').classList.remove('hidden');
  document.getElementById('sim-results').classList.add('hidden');
  document.getElementById('sim-results').innerHTML = '';
  document.getElementById('sim-scenario').value = '';
}

function closeSimulator() {
  document.getElementById('sim-modal').classList.add('hidden');
}

function setScenario(text) {
  document.getElementById('sim-scenario').value = text;
}

async function runSimulation() {
  const scenario = document.getElementById('sim-scenario').value.trim();
  if (!scenario) { alert('Please describe a scenario to simulate.'); return; }
  if (!analysisData) { alert('Please run a compliance analysis first.'); return; }

  const btn = document.getElementById('sim-btn');
  btn.disabled = true;
  document.getElementById('sim-loading').classList.remove('hidden');
  document.getElementById('sim-results').classList.add('hidden');

  try {
    const resp = await fetch(`${API}/api/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scenario,
        bank_name: analysisData.bank_name,
        regulation_name: analysisData.regulation_name,
        compliance_score: analysisData.compliance_score,
        fully_covered: analysisData.fully_covered,
        partially_covered: analysisData.partially_covered,
        not_covered: analysisData.not_covered,
        gaps: analysisData.gaps,
        controls: analysisData.controls,
      }),
    });
    if (!resp.ok) throw new Error(await resp.text());
    const sim = await resp.json();
    renderSimulation(sim);
  } catch (err) {
    const msg = err.message.includes('Not Found')
      ? 'Simulation endpoint not available.\n\nPlease restart the server:\n  Stop it (Ctrl+C) and run: python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload'
      : 'Simulation failed: ' + err.message;
    alert(msg);
  } finally {
    btn.disabled = false;
    document.getElementById('sim-loading').classList.add('hidden');
  }
}

function renderSimulation(sim) {
  const deltaSign = sim.score_delta >= 0 ? '+' : '';
  const deltaColor = sim.score_delta >= 0 ? 'var(--success)' : 'var(--danger)';

  let newGapsHtml = (sim.newly_created_gaps || []).map(g => `
    <div class="sim-gap">
      <span class="risk-badge risk-${g.risk_level}">${g.risk_level}</span>
      <span>${g.description}</span>
    </div>`).join('') || '<em style="color:var(--success)">No new gaps created.</em>';

  let actionsHtml = (sim.required_actions || []).map(a => `
    <div class="sim-action">
      <span class="rem-tag" style="margin-right:0.4rem">${a.priority}</span>
      ${a.action} <em>(Effort: ${a.effort})</em>
    </div>`).join('');

  const container = document.getElementById('sim-results');
  container.innerHTML = `
    <div class="sim-narrative">${sim.simulation_narrative}</div>
    <div class="sim-score-row">
      <div class="sim-score-block">
        <div class="sim-score-val">${sim.new_compliance_score}%</div>
        <div>Projected Score</div>
      </div>
      <div class="sim-score-block">
        <div class="sim-score-val" style="color:${deltaColor}">${deltaSign}${sim.score_delta}%</div>
        <div>Score Change</div>
      </div>
      <div class="sim-score-block">
        <div class="sim-score-val" style="color:var(--danger)">${(sim.newly_created_gaps || []).length}</div>
        <div>New Gaps</div>
      </div>
      <div class="sim-score-block">
        <div class="sim-score-val" style="color:var(--success)">${(sim.closed_gaps || []).length}</div>
        <div>Gaps Resolved</div>
      </div>
    </div>
    <div class="sim-section-title">New Compliance Gaps</div>
    <div class="sim-gaps">${newGapsHtml}</div>
    <div class="sim-section-title">Required Actions</div>
    <div class="sim-actions">${actionsHtml}</div>`;
  container.classList.remove('hidden');
}

// ── Regulatory Change Intelligence ────────────────────────────────────────────

async function runChangeAnalysis() {
  const oldFile = document.getElementById('old-reg-file').files[0];
  const newFile = document.getElementById('new-reg-file').files[0];
  const oldText = document.getElementById('old-reg-text').value.trim();
  const newText = document.getElementById('new-reg-text').value.trim();
  const regName = document.getElementById('change-reg-name').value;

  if (!oldFile && !oldText) { alert('Please provide the previous regulation version.'); return; }
  if (!newFile && !newText) { alert('Please provide the new regulation version.'); return; }

  document.getElementById('change-loading').classList.remove('hidden');
  document.getElementById('change-results').classList.add('hidden');
  document.getElementById('change-analyze-btn').disabled = true;

  try {
    // For file uploads in change mode, read as text client-side (simple approach)
    const getText = async (file, fallback) => {
      if (file) {
        return new Promise((resolve) => {
          const reader = new FileReader();
          reader.onload = e => resolve(e.target.result);
          reader.readAsText(file);
        });
      }
      return fallback;
    };

    const resolvedOld = await getText(oldFile, oldText);
    const resolvedNew = await getText(newFile, newText);

    const resp = await fetch(`${API}/api/change-analysis`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        old_regulation_text: resolvedOld,
        new_regulation_text: resolvedNew,
        regulation_name: regName,
      }),
    });
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    renderChangeResults(data);
  } catch (err) {
    alert('Change analysis failed: ' + err.message);
  } finally {
    document.getElementById('change-loading').classList.add('hidden');
    document.getElementById('change-analyze-btn').disabled = false;
  }
}

function renderChangeResults(data) {
  document.getElementById('change-impact-summary').textContent = data.impact_summary;
  document.getElementById('chg-total').textContent = data.total_changes;
  document.getElementById('chg-critical').textContent = data.critical_changes;
  document.getElementById('chg-high').textContent = data.high_impact_changes;

  const container = document.getElementById('changes-list');
  container.innerHTML = '';
  (data.changes || []).forEach(chg => {
    const impColor = chg.impact_level === 'Critical' ? 'var(--danger)' :
                     chg.impact_level === 'High' ? 'var(--warning)' :
                     chg.impact_level === 'Medium' ? 'var(--accent)' : 'var(--text-muted)';
    const typeIcon = chg.change_type === 'New Requirement' ? '🆕' :
                     chg.change_type === 'Removed Requirement' ? '🗑️' :
                     chg.change_type === 'Stricter Enforcement' ? '⬆️' :
                     chg.change_type === 'Relaxed Enforcement' ? '⬇️' : '✏️';
    const div = document.createElement('div');
    div.className = 'change-card';
    div.innerHTML = `
      <div class="change-header">
        <span class="change-id">${chg.id}</span>
        <span class="change-type-badge">${typeIcon} ${chg.change_type}</span>
        <span class="risk-badge risk-${chg.impact_level}" style="margin-left:auto">${chg.impact_level}</span>
        <span style="font-size:0.8rem;color:var(--text-muted);margin-left:0.75rem">${chg.section_ref || ''}</span>
      </div>
      <div class="change-desc">${chg.description}</div>
      <div class="change-action">
        <strong>Action required:</strong> ${chg.compliance_action}
        <span class="rem-tag" style="margin-left:0.75rem">⏱️ ${chg.implementation_timeline}</span>
      </div>
      ${(chg.affected_categories || []).length ? `
      <div class="change-cats">${chg.affected_categories.map(c => `<span class="cat-tag">${c}</span>`).join('')}</div>` : ''}`;
    container.appendChild(div);
  });

  document.getElementById('change-results').classList.remove('hidden');
}

// ── Sample data helpers ───────────────────────────────────────────────────────

const SAMPLE_REGULATION = `RBI Master Direction on Know Your Customer (KYC) - Updated 2024

Section 1: Customer Identification
1.1 All banks shall identify their customers before opening accounts. Banks must obtain officially valid documents (OVDs) for establishing identity and address.
1.2 Banks shall carry out fresh KYC of existing customers at periodic intervals: High Risk - every 2 years, Medium Risk - every 8 years, Low Risk - every 10 years.
1.3 Aadhaar authentication must be performed for individual customers where applicable.

Section 2: Customer Due Diligence (CDD)
2.1 Banks shall implement a risk-based Customer Due Diligence (CDD) program categorizing customers into High, Medium, and Low risk.
2.2 Enhanced Due Diligence (EDD) must be applied to Politically Exposed Persons (PEPs), non-resident customers, and customers from high-risk countries.
2.3 Beneficial ownership must be identified for all legal entities with ownership threshold of 25% or more.

Section 3: Anti-Money Laundering (AML)
3.1 Banks must maintain a robust AML program including transaction monitoring systems to detect suspicious activity.
3.2 Banks shall file Suspicious Transaction Reports (STRs) with Financial Intelligence Unit India (FIU-IND) within 7 days of detecting suspicious activity.
3.3 Cash Transaction Reports (CTRs) must be filed for all transactions above INR 10 lakhs.

Section 4: Record Keeping
4.1 Banks shall maintain KYC records for at least 10 years after the end of the customer relationship.
4.2 Transaction records must be maintained for at least 5 years from the date of transaction.
4.3 All records must be available for inspection by RBI regulators within 48 hours of request.

Section 5: Technology and Data
5.1 Banks must implement a centralised KYC utility or use CKYC Registry for storing and retrieving KYC records.
5.2 KYC data must be encrypted at rest and in transit using approved encryption standards.
5.3 Banks shall implement multi-factor authentication for access to KYC systems.

Section 6: Governance
6.1 Banks must designate a Principal Officer responsible for KYC/AML compliance.
6.2 Board-level KYC/AML policy must be reviewed and approved annually.
6.3 Staff must receive KYC/AML training at least once a year.`;

const SAMPLE_CONTROLS = `Sample Bank Ltd. - Internal Compliance Policy Framework v2.3

Chapter 1: Customer Onboarding Controls
CTL-A: New Customer Identification Procedure
All new customers must submit two forms of officially valid documents (OVDs) — one for identity and one for address — before account opening. Documents are verified against RBI-approved OVD list.

CTL-B: Digital KYC Process
The bank utilizes Aadhaar-based eKYC for individual customers. Biometric and OTP-based authentication is supported through UIDAI integration.

CTL-C: Periodic KYC Review
Customer KYC is reviewed periodically: High Risk customers every 3 years, Medium Risk every 8 years, Low Risk every 10 years. Reviews are tracked in the core banking system.

Chapter 2: Risk Classification
CTL-D: Customer Risk Rating
All customers are assigned a risk rating (High/Medium/Low) at onboarding based on occupation, transaction profile, and geography. Risk ratings are reviewed annually.

Chapter 3: Transaction Monitoring
CTL-E: AML Transaction Monitoring System
The bank has deployed an automated AML transaction monitoring system (AMLS) that flags suspicious transactions based on rule-based and ML models. Alerts are reviewed by the AML team within 3 business days.

Chapter 4: Reporting
CTL-F: STR and CTR Filing Process
The bank has a designated Compliance Officer responsible for filing Suspicious Transaction Reports (STRs) and Cash Transaction Reports (CTRs) with FIU-IND. CTRs are filed for transactions above INR 10 lakhs. STRs are filed within the regulatory timeline.

Chapter 5: Record Management
CTL-G: Record Retention Policy
Customer KYC records are retained for 10 years. Transaction records are retained for 5 years. Records are stored in encrypted digital format.

Chapter 6: Governance and Training
CTL-H: KYC/AML Governance Framework
The bank has appointed a Principal Compliance Officer. Board-approved KYC Policy is reviewed annually. All staff complete mandatory AML training during induction.`;

const SAMPLE_OLD_REGULATION = `RBI Master Direction on KYC - 2022 Version

Section 1: Customer Identification
1.1 Banks shall identify customers before opening accounts using officially valid documents.
1.2 Periodic KYC refresh: High Risk every 2 years, Medium Risk every 8 years, Low Risk every 10 years.

Section 2: AML Requirements
2.1 Banks must maintain AML transaction monitoring programs.
2.2 STRs must be filed with FIU-IND within 7 days.
2.3 CTRs required for transactions above INR 10 lakhs.

Section 3: Record Keeping
3.1 KYC records retained for 10 years.
3.2 Transaction records retained for 5 years.

Section 4: Governance
4.1 Banks must designate a Principal Officer for KYC/AML.
4.2 Board policy reviewed annually.`;

const SAMPLE_NEW_REGULATION = `RBI Master Direction on KYC - 2024 Revised Version

Section 1: Customer Identification
1.1 Banks shall identify customers before opening accounts using officially valid documents. Video KYC (V-CIP) is now an approved alternative channel.
1.2 Periodic KYC refresh: High Risk every 1 year (AMENDED from 2 years), Medium Risk every 5 years (AMENDED from 8 years), Low Risk every 10 years.
1.3 NEW: Real-time biometric verification required for high-risk customer onboarding.

Section 2: AML Requirements
2.1 Banks must maintain AI-powered AML transaction monitoring — manual rule-based systems no longer sufficient.
2.2 STRs must now be filed within 3 days (AMENDED from 7 days) — stricter timeline.
2.3 CTRs required for transactions above INR 10 lakhs. NEW: Digital asset transactions above INR 5 lakhs also require CTR filing.
2.4 NEW: Cross-border wire transfers above USD 10,000 require enhanced monitoring and reporting.

Section 3: Record Keeping
3.1 KYC records retained for 10 years.
3.2 Transaction records retained for 8 years (AMENDED from 5 years).
3.3 NEW: Records must be available within 2 hours for regulator inspection (AMENDED from 48 hours).

Section 4: Cybersecurity — NEW SECTION
4.1 Banks must implement zero-trust architecture for KYC systems by March 2025.
4.2 Annual third-party penetration testing of KYC infrastructure is mandatory.
4.3 Incident reporting to RBI within 6 hours for any KYC data breach.

Section 5: Governance
5.1 Banks must designate a Principal Officer for KYC/AML.
5.2 Board policy reviewed semi-annually (AMENDED from annually).
5.3 NEW: External audit of KYC/AML program required every 2 years.`;

function loadSampleData() {
  document.getElementById('reg-text').value = SAMPLE_REGULATION;
  document.getElementById('ctl-text').value = SAMPLE_CONTROLS;
  document.getElementById('reg-name').value = 'RBI Master Direction on KYC 2024';
  document.getElementById('bank-name').value = 'Sample Bank Ltd.';
  document.getElementById('reg-filename').textContent = 'No file chosen';
  document.getElementById('ctl-filename').textContent = 'No file chosen';
}

function loadChangeSample() {
  document.getElementById('old-reg-text').value = SAMPLE_OLD_REGULATION;
  document.getElementById('new-reg-text').value = SAMPLE_NEW_REGULATION;
  document.getElementById('change-reg-name').value = 'RBI Master Direction on KYC';
}

// Close modal on overlay click
document.getElementById('sim-modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeSimulator();
});
