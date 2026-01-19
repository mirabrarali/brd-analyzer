const statusEl = document.getElementById('status');
const analyzeBtn = document.getElementById('analyzeBtn');
const fileEl = document.getElementById('file');
const outputEl = document.getElementById('output');

function setStatus(msg) {
  statusEl.textContent = msg;
}

analyzeBtn.addEventListener('click', async () => {
  const file = fileEl.files && fileEl.files[0];
  if (!file) {
    setStatus('Please select a PDF or DOCX file.');
    return;
  }

  const output = outputEl.value;
  const fd = new FormData();
  fd.append('file', file);

  setStatus('Analyzing document... This may take 20-40 seconds.');
  analyzeBtn.disabled = true;

  try {
    const res = await fetch(`/api/analyze?output=${encodeURIComponent(output)}`, {
      method: 'POST',
      body: fd,
    });

    if (!res.ok) {
      let detail = '';
      try {
        const j = await res.json();
        detail = j.detail ? `: ${j.detail}` : '';
      } catch {
        // ignore
      }
      setStatus(`Analysis failed${detail}`);
      analyzeBtn.disabled = false;
      return;
    }

    const blob = await res.blob();
    const cd = res.headers.get('content-disposition') || '';
    const match = cd.match(/filename="([^"]+)"/);
    const filename = match ? match[1] : 'brd-analysis-report.pdf';

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);

    setStatus('Report generated successfully.');
  } catch (e) {
    setStatus('Request failed. Please try again.');
  }
  analyzeBtn.disabled = false;
});
