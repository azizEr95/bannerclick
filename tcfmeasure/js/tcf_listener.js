// Runs as a Selenium script in the top frame. Registers one __tcfapi('addEventListener') per page
// and collects every event in window.__tcfmeasureLog. Returns the log collected so far (or null
// if __tcfapi does not exist yet). Calling it again does not register a second listener.
// The CMP answers addEventListener immediately with the current state, so even when the listener
// is registered late, the first entry is the state at registration time.
if (typeof window.__tcfapi !== 'function') return null;

if (!window.__tcfmeasureLog) {
  window.__tcfmeasureLog = [];
  const ids = (map) => map ? Object.keys(map).filter((id) => map[id] === true).map(Number) : null;
  window.__tcfapi('addEventListener', 2, (tcData, success) => {
    if (!success || !tcData) return;
    window.__tcfmeasureLog.push({
      time: Date.now(),
      eventStatus: tcData.eventStatus || null,
      cmpStatus: tcData.cmpStatus || null,
      gdprApplies: tcData.gdprApplies,
      tcString: tcData.tcString || null,
      purposeConsents: ids(tcData.purpose && tcData.purpose.consents),
      purposeLegitimateInterests: ids(tcData.purpose && tcData.purpose.legitimateInterests),
      vendorConsents: ids(tcData.vendor && tcData.vendor.consents),
      vendorLegitimateInterests: ids(tcData.vendor && tcData.vendor.legitimateInterests),
      specialFeatureOptins: ids(tcData.specialFeatureOptins),
      publisherConsents: ids(tcData.publisher && tcData.publisher.consents),
      publisherLegitimateInterests: ids(tcData.publisher && tcData.publisher.legitimateInterests),
      raw: JSON.stringify(tcData),
    });
  });
}
return window.__tcfmeasureLog;
