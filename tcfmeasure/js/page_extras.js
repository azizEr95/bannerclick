// Runs as a Selenium script in the top frame.
// arguments[0] = "storage": localStorage entries whose value looks like a TC string.
// arguments[0] = "gdpr_consent": URLs of requests with gdpr_consent= (Resource Timing, top frame only).
const mode = arguments[0];
const TC_STRING = /^C[A-Za-z0-9_-]{20,}(\.[A-Za-z0-9_-]+)*$/;

if (mode === 'storage') {
  const found = [];
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      let value = localStorage.getItem(key) || '';
      try { const parsed = JSON.parse(value); if (typeof parsed === 'string') value = parsed; } catch (e) {}
      if (TC_STRING.test(value)) found.push({ name: 'localStorage:' + key, value: value });
    }
  } catch (e) {}
  return found;
}

if (mode === 'gdpr_consent') {
  try { performance.setResourceTimingBufferSize(10000); } catch (e) {}
  return performance.getEntriesByType('resource').map((entry) => entry.name)
    .filter((url) => /[?&]gdpr_consent=/.test(url));
}
return null;
