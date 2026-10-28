// Runs as a Selenium script in one frame. Returns the visible consent controls of this frame,
// including open shadow roots:
//   buttons: [{element, label}]  clickable elements inside a consent context
//   toggles: [{element, clickTarget, checked, disabled, label}]  checkboxes and switches
// A consent context is an ancestor (up to 8 levels, at most 5000 characters of text) that
// mentions cookies, consent, purposes etc.; this keeps "Ablehnen" buttons of other widgets out.
const CONSENT_CONTEXT = /cookie|einwillig|zustimm|datenschutz|privacy|consent|zweck|purpose|partner|tracking|personalisier/i;
const BUTTON_SELECTOR = 'button, a, [role="button"], input[type="button"], input[type="submit"]';
const TOGGLE_SELECTOR = 'input[type="checkbox"], [role="switch"], [role="checkbox"]';

function* allElements(root) {
  for (const element of root.querySelectorAll('*')) {
    yield element;
    if (element.shadowRoot) yield* allElements(element.shadowRoot);
  }
}

function isVisible(element, ignoreOpacity = false) {
  if (!element || !element.getBoundingClientRect) return false;
  const rect = element.getBoundingClientRect();
  if (rect.width < 2 || rect.height < 2) return false;
  const style = getComputedStyle(element);
  if (style.visibility === 'hidden' || style.display === 'none') return false;
  return ignoreOpacity || parseFloat(style.opacity) > 0.05;
}

// Transparent <input> laid over a visible button text (e.g. Amazon): the input itself has
// opacity 0, so it counts as visible when it has a size and its parent is visible.
function isClickable(element) {
  if (isVisible(element)) return true;
  return element.tagName === 'INPUT' && isVisible(element, true) && isVisible(parentOf(element));
}

function parentOf(element) {
  return element.parentElement || (element.getRootNode() && element.getRootNode().host) || null;
}

function inConsentContext(element) {
  let ancestor = element;
  for (let i = 0; i < 8 && ancestor; i++) {
    const text = ancestor.textContent || '';  // textContent: no layout, fast on large pages
    if (text.length > 5000) return false;
    if (CONSENT_CONTEXT.test(text)) return true;
    ancestor = parentOf(ancestor);
  }
  return false;
}

function clean(text) {
  return (text || '').trim().replace(/\s+/g, ' ').slice(0, 200);
}

function labelledByText(element) {
  const ids = (element.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
  return ids.map((id) => document.getElementById(id)).filter(Boolean).map((el) => el.innerText).join(' ');
}

function labelOf(element) {
  const own = element.innerText || element.value || element.getAttribute('aria-label')
    || labelledByText(element) || element.title;
  if (clean(own)) return clean(own);
  // E.g. Amazon: an <input> without text inside a wrapper that shows the label.
  const parent = parentOf(element);
  const parentText = parent ? clean(parent.innerText) : '';
  return parentText.length <= 60 ? parentText : '';
}

function toggleLabel(toggle) {
  if (toggle.getAttribute('aria-label')) return toggle.getAttribute('aria-label');
  if (toggle.labels && toggle.labels.length) return labelOf(toggle.labels[0]);
  // Otherwise the text of the nearest row around the toggle.
  let ancestor = parentOf(toggle);
  for (let i = 0; i < 4 && ancestor; i++) {
    const text = labelOf(ancestor);
    if (text) return text;
    ancestor = parentOf(ancestor);
  }
  return '';
}

function isChecked(toggle) {
  if (typeof toggle.checked === 'boolean') return toggle.checked;
  return toggle.getAttribute('aria-checked') === 'true';
}

function isDisabled(toggle) {
  return toggle.disabled === true || toggle.getAttribute('aria-disabled') === 'true';
}

// Custom switches often hide the real <input>; then its label or a parent is what the user clicks.
function clickTargetOf(toggle) {
  const candidates = [toggle, toggle.labels && toggle.labels[0], parentOf(toggle)];
  return candidates.find(isVisible) || null;
}

const buttons = [];
const toggles = [];
for (const element of allElements(document)) {
  if (element.matches(BUTTON_SELECTOR) && isClickable(element)) {
    const label = labelOf(element);
    if (label && label.length <= 80 && inConsentContext(element)) buttons.push({ element, label });
  }
  if (element.matches(TOGGLE_SELECTOR)) {
    const clickTarget = clickTargetOf(element);
    if (clickTarget && inConsentContext(clickTarget)) {
      toggles.push({
        element, clickTarget,
        checked: isChecked(element), disabled: isDisabled(element), label: toggleLabel(element),
      });
    }
  }
}
// The banner of this frame: the smallest element containing all consent buttons.
// Its text and HTML are used for the cookiewall check.
function ancestors(element) {
  const list = [];
  for (let a = element; a; a = parentOf(a)) list.push(a);
  return list;
}
let banner = null;
if (buttons.length) {
  const shared = ancestors(buttons[0].element);
  banner = shared.find((candidate) => buttons.every((b) => ancestors(b.element).includes(candidate)));
}
const bannerText = banner ? (banner.innerText || '').slice(0, 20000) : '';
const bannerHtml = banner && banner.outerHTML ? banner.outerHTML.slice(0, 200000) : '';

return { buttons, toggles, bannerText, bannerHtml };
