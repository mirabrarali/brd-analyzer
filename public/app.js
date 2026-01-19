const statusEl = document.getElementById('status');
const analyzeBtn = document.getElementById('analyzeBtn');
const sampleBtn = document.getElementById('sampleBtn');
const fileEl = document.getElementById('file');
const outputEl = document.getElementById('output');
const previewCard = document.getElementById('previewCard');
const previewEl = document.getElementById('preview');

function setStatus(msg) {
  statusEl.textContent = msg;
}

function showPreview(obj) {
  previewCard.style.display = 'block';
  previewEl.textContent = JSON.stringify(obj, null, 2);
}

function hidePreview() {
  previewCard.style.display = 'none';
  previewEl.textContent = '';
}

sampleBtn.addEventListener('click', async () => {
  hidePreview();
  setStatus('Checking /api/health ...');
  try {
    const res = await fetch('/api/health');
    const json = await res.json();
    setStatus(res.ok ? 'API OK' : 'API error');
    showPreview(json);
  } catch (e) {
    setStatus('Failed to reach API.');
  }
});

analyzeBtn.addEventListener('click', async () => {
  hidePreview();

  const file = fileEl.files && fileEl.files[0];
  if (!file) {
    setStatus('Please choose a PDF or DOCX file.');
    return;
  }

  const output = outputEl.value;
  const fd = new FormData();
  fd.append('file', file);

  setStatus('Uploading and analyzing (this can take ~10-40s) ...');

  try {
    const res = await fetch(`/api/analyze?output=${encodeURIComponent(output)}`, {
      method: 'POST',
      body: fd,
    });

    if (!res.ok) {
      let detail = '';
      try {
        const j = await res.json();
        detail = j.detail ? ` ${j.detail}` : '';
      } catch {
        // ignore
      }
      setStatus(`Analyze failed.${detail}`);
      return;
    }

    if (output === 'json') {
      const json = await res.json();
      setStatus('Done (JSON).');
      showPreview(json);
      return;
    }

    const blob = await res.blob();
    const cd = res.headers.get('content-disposition') || '';
    const match = cd.match(/filename="([^"]+)"/);
    const filename = match ? match[1] : 'brd-report.pdf';

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);

    setStatus('Done. Download started.');
  } catch (e) {
    setStatus('Request failed.');
  }
});
