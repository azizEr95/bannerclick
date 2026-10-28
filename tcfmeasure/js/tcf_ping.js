// Runs as a Selenium async script in the top frame.
// arguments[0]: timeout in ms for the ping call; last argument: Selenium callback.
// Finds the TCF API either as the __tcfapi function or, if only the __tcfapiLocator frame
// exists, via the postMessage interface of the TCF spec, and returns the ping result.
const timeoutMs = arguments[0];
const done = arguments[arguments.length - 1];

const hasFunction = typeof window.__tcfapi === 'function';
let hasLocator = false;
try {
  hasLocator = Boolean(window.frames['__tcfapiLocator'])
    || document.querySelector('iframe[name="__tcfapiLocator"]') !== null;
} catch (e) {}

const result = { has_tcfapi: hasFunction, has_locator: hasLocator, ping: null, ping_via: null };

let finished = false;
const finish = () => {
  if (finished) return;
  finished = true;
  done(result);
};
setTimeout(finish, timeoutMs);

if (hasFunction) {
  try {
    window.__tcfapi('ping', 2, (pingReturn) => {
      result.ping = pingReturn || null;
      result.ping_via = 'function';
      finish();
    });
  } catch (e) {
    finish();
  }
} else if (hasLocator) {
  // The CMP that created the locator frame listens for __tcfapiCall messages on this window.
  const callId = 'tcfmeasure-' + Math.random().toString(36).slice(2);
  window.addEventListener('message', (event) => {
    let data = event.data;
    try { if (typeof data === 'string') data = JSON.parse(data); } catch (e) { return; }
    if (data && data.__tcfapiReturn && data.__tcfapiReturn.callId === callId) {
      result.ping = data.__tcfapiReturn.returnValue || null;
      result.ping_via = 'postMessage';
      finish();
    }
  });
  window.postMessage({ __tcfapiCall: { command: 'ping', version: 2, callId: callId } }, '*');
} else {
  finish();
}
