'use strict';

const $ = (id) => document.getElementById(id);
const state = {
  file: null,
  jobId: null,
  poll: null,
  duration: 0,
  split: 0.5,
  lens: [0.5, 0.5],
};

/* ---------------------------------------------------------------- helpers */

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body && body.detail) detail = body.detail;
    } catch (_) { /* not JSON; keep the status line */ }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const fmtBytes = (n) => n > 1e9 ? `${(n / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(n / 1e6))} MB`;

/* --------------------------------------------------------------- controls */

const SLIDERS = [
  ['strength', 'strength', (v) => `${Math.round(v * 100)}%`],
  ['falloff', 'falloff_start_deg', (v) => `${v}°`],
  ['maxcorr', 'max_correction_deg', (v) => `${v}°`],
  ['fov', 'fov_deg', (v) => `${v}°`],
  ['faces', 'max_faces', (v) => `${v}`],
];

function syncOutputs() {
  for (const [id, , format] of SLIDERS) {
    $(`${id}-out`).textContent = format(parseFloat($(id).value));
  }
  $('lens-out').textContent = `x ${state.lens[0].toFixed(2)}, y ${state.lens[1].toFixed(2)}`;
  const marker = $('lens-marker');
  // The pad shows a region wider than the frame so the lens can sit outside it.
  marker.style.left = `${((state.lens[0] * 0.56) + 0.22) * 100}%`;
  marker.style.top = `${((state.lens[1] * 0.56) + 0.22) * 100}%`;
}

function collectSettings() {
  const settings = { lens_position: state.lens, auto_calibrate: $('calibrate').checked };
  for (const [id, key] of SLIDERS) {
    const value = parseFloat($(id).value);
    settings[key] = key === 'max_faces' ? Math.round(value) : value;
  }
  // The server rejects a fade that starts after the cutoff, so keep them ordered.
  if (settings.falloff_start_deg > settings.max_correction_deg) {
    settings.falloff_start_deg = settings.max_correction_deg;
  }
  return settings;
}

async function loadDefaults() {
  try {
    const defaults = await api('/api/defaults');
    for (const [id, key] of SLIDERS) {
      if (defaults[key] !== undefined) $(id).value = defaults[key];
    }
    $('calibrate').checked = defaults.auto_calibrate !== false;
    state.lens = defaults.lens_position || [0.5, 0.5];
  } catch (err) {
    console.warn('falling back to built-in defaults:', err.message);
    $('strength').value = 1; $('falloff').value = 11; $('maxcorr').value = 16;
    $('fov').value = 60; $('faces').value = 1; $('calibrate').checked = true;
  }
  syncOutputs();
}

async function loadHealth() {
  try {
    const health = await api('/api/health');
    if (health.notes && health.notes.length) {
      $('health').textContent = health.notes.join(' ');
      $('health').hidden = false;
    }
  } catch (_) { /* the banner is optional */ }
}

/* ----------------------------------------------------------------- upload */

function pickFile(file) {
  state.file = file;
  $('picked').textContent = file ? `${file.name} · ${fmtBytes(file.size)}` : '';
  $('submit').disabled = !file;
  $('submit-error').hidden = true;
}

function wireUpload() {
  const drop = $('drop');
  $('file').addEventListener('change', (e) => pickFile(e.target.files[0] || null));
  ['dragenter', 'dragover'].forEach((type) => drop.addEventListener(type, (e) => {
    e.preventDefault();
    drop.classList.add('over');
  }));
  ['dragleave', 'drop'].forEach((type) => drop.addEventListener(type, (e) => {
    e.preventDefault();
    drop.classList.remove('over');
  }));
  drop.addEventListener('drop', (e) => {
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (file) pickFile(file);
  });
}

/* ------------------------------------------------------------- lens picker */

function wireLensPad() {
  const pad = $('lens-pad');
  let dragging = false;

  const place = (event) => {
    const rect = pad.getBoundingClientRect();
    // Invert the mapping used when drawing the marker, so the inner 56% of the
    // pad is the frame itself and the margin is off-frame territory.
    const x = (((event.clientX - rect.left) / rect.width) - 0.22) / 0.56;
    const y = (((event.clientY - rect.top) / rect.height) - 0.22) / 0.56;
    state.lens = [
      Math.round(clamp(x, -0.6, 1.6) * 100) / 100,
      Math.round(clamp(y, -0.6, 1.6) * 100) / 100,
    ];
    syncOutputs();
  };

  pad.addEventListener('pointerdown', (e) => {
    dragging = true;
    pad.setPointerCapture(e.pointerId);
    place(e);
  });
  pad.addEventListener('pointermove', (e) => { if (dragging) place(e); });
  pad.addEventListener('pointerup', () => { dragging = false; });
  $('lens-reset').addEventListener('click', () => {
    state.lens = [0.5, 0.5];
    syncOutputs();
  });
}

/* ---------------------------------------------------------------- compare */

function refreshPreview() {
  if (!state.jobId) return;
  const t = parseFloat($('scrub').value) / 100 * (state.duration || 0);
  $('scrub-out').textContent = `${t.toFixed(1)}s`;
  const url = `/api/jobs/${state.jobId}/preview?mode=split`
    + `&t=${t.toFixed(3)}&split=${state.split.toFixed(3)}`;
  $('compare-img').src = url;
}

function wireCompare() {
  const stage = $('compare-stage');
  let dragging = false;

  const move = (event) => {
    const rect = stage.getBoundingClientRect();
    state.split = clamp((event.clientX - rect.left) / rect.width, 0, 1);
    $('compare-handle').style.left = `${state.split * 100}%`;
  };

  stage.addEventListener('pointerdown', (e) => {
    dragging = true;
    stage.setPointerCapture(e.pointerId);
    move(e);
  });
  stage.addEventListener('pointermove', (e) => { if (dragging) move(e); });
  stage.addEventListener('pointerup', () => {
    if (!dragging) return;
    dragging = false;
    refreshPreview();
  });

  let scrubTimer = null;
  $('scrub').addEventListener('input', () => {
    clearTimeout(scrubTimer);
    scrubTimer = setTimeout(refreshPreview, 120);
  });
}

/* -------------------------------------------------------------- job flow */

const STAT_FIELDS = [
  ['frames', (s) => s.frames],
  ['frames with a face', (s) => s.frames_with_face],
  ['frames corrected', (s) => s.frames_corrected],
  ['mean offset', (s) => `${s.mean_offset_deg}°`],
  ['peak offset', (s) => `${s.peak_offset_deg}°`],
  ['mean eye shift', (s) => `${s.mean_iris_shift_px} px`],
];

function renderDone(job) {
  const report = job.report || {};
  const stats = report.stats || {};
  $('player').src = `/api/jobs/${job.id}/result`;
  $('download').href = `/api/jobs/${job.id}/result`;

  $('stats').innerHTML = STAT_FIELDS
    .map(([label, get]) => `<div><dt>${label}</dt><dd>${get(stats)}</dd></div>`)
    .join('');

  const notes = (report.warnings || []).slice();
  const calibration = report.calibration || {};
  if (calibration.converged) {
    notes.unshift(`Calibrated this subject's eye anatomy from ${calibration.samples} frames `
      + `(anchor ${calibration.outer_corner_weight} against a default of `
      + `${calibration.default_weight}).`);
  }
  $('warnings').innerHTML = notes.map((n) => `<p class="note">${n}</p>`).join('');
  $('raw-report').textContent = JSON.stringify(report, null, 2);
  $('done').hidden = false;
}

function renderJob(job) {
  $('job-panel').hidden = false;
  $('job-name').textContent = job.filename;
  $('cancel').hidden = false;

  const percent = Math.round((job.progress || 0) * 100);
  $('progress-bar').style.width = `${percent}%`;

  if (job.status === 'failed') {
    $('job-stage').textContent = `failed — ${job.error || 'unknown error'}`;
    return;
  }
  if (job.status === 'done') {
    const elapsed = (job.report && job.report.elapsed_s) || 0;
    $('job-stage').textContent = `done in ${elapsed}s`;
    renderDone(job);
    return;
  }
  $('job-stage').textContent = `${job.stage}… ${percent}%`;
}

function stopPolling() {
  if (state.poll) clearInterval(state.poll);
  state.poll = null;
}

async function pollJob() {
  try {
    const job = await api(`/api/jobs/${state.jobId}`);
    renderJob(job);
    if (job.status === 'done' || job.status === 'failed') {
      stopPolling();
      loadHistory();
    }
  } catch (err) {
    stopPolling();
    $('job-stage').textContent = `lost track of this job: ${err.message}`;
  }
}

async function submit() {
  if (!state.file) return;
  $('submit').disabled = true;
  $('submit-error').hidden = true;
  $('done').hidden = true;
  $('compare').hidden = true;
  stopPolling();

  const body = new FormData();
  body.append('file', state.file);
  body.append('settings', JSON.stringify(collectSettings()));

  try {
    const job = await api('/api/jobs', { method: 'POST', body });
    state.jobId = job.id;
    state.split = 0.5;
    $('compare-handle').style.left = '50%';
    renderJob(job);

    // Read the clip's length locally so the scrubber can map to seconds without
    // waiting for the run to finish.
    const probe = document.createElement('video');
    probe.preload = 'metadata';
    probe.onloadedmetadata = () => {
      state.duration = probe.duration || 0;
      URL.revokeObjectURL(probe.src);
      $('compare').hidden = false;
      refreshPreview();
    };
    probe.src = URL.createObjectURL(state.file);

    state.poll = setInterval(pollJob, 1000);
  } catch (err) {
    $('submit-error').textContent = err.message;
    $('submit-error').hidden = false;
  } finally {
    $('submit').disabled = !state.file;
  }
}

async function loadHistory() {
  try {
    const { jobs } = await api('/api/jobs');
    const others = jobs.filter((j) => j.id !== state.jobId);
    $('history-panel').hidden = others.length === 0;
    $('history').innerHTML = others.map((job) => {
      const when = new Date(job.created_at * 1000).toLocaleString();
      const link = job.status === 'done'
        ? `<a href="/api/jobs/${job.id}/result" download>download</a>`
        : `<span class="meta">${job.status}</span>`;
      return `<li><div><div>${job.filename}</div><div class="meta">${when}</div></div>${link}</li>`;
    }).join('');
  } catch (_) { /* history is a convenience */ }
}

async function discard() {
  if (!state.jobId) return;
  stopPolling();
  try {
    await api(`/api/jobs/${state.jobId}`, { method: 'DELETE' });
  } catch (_) { /* already gone */ }
  state.jobId = null;
  $('job-panel').hidden = true;
  $('done').hidden = true;
  $('compare').hidden = true;
  $('player').removeAttribute('src');
  loadHistory();
}

/* ------------------------------------------------------------------- init */

for (const [id] of SLIDERS) $(id).addEventListener('input', syncOutputs);
$('submit').addEventListener('click', submit);
$('cancel').addEventListener('click', discard);
wireUpload();
wireLensPad();
wireCompare();
loadDefaults();
loadHealth();
loadHistory();
