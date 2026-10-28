// Decodes TC strings with the official IAB Tech Lab library (@iabtechlabtcf/core).
// Input on stdin: one TC string per line. Output on stdout: one JSON object per line, same order.
// Consent vectors are written as sorted lists of the IDs that are set.
import { createRequire } from 'module';
import { readFileSync } from 'fs';

const require = createRequire(import.meta.url);
const { TCString } = require('@iabtechlabtcf/core');

function ids(vector) {
  const set = [];
  if (vector) vector.forEach((value, id) => { if (value) set.push(id); });
  return set.sort((a, b) => a - b);
}

function decode(tcString) {
  try {
    const model = TCString.decode(tcString);
    return {
      tc_string: tcString,
      error: null,
      version: model.version,
      created: model.created ? model.created.toISOString() : null,
      last_updated: model.lastUpdated ? model.lastUpdated.toISOString() : null,
      cmp_id: model.cmpId,
      cmp_version: model.cmpVersion,
      consent_screen: model.consentScreen,
      consent_language: model.consentLanguage,
      vendor_list_version: model.vendorListVersion,
      policy_version: model.policyVersion,
      is_service_specific: model.isServiceSpecific,
      purpose_one_treatment: model.purposeOneTreatment,
      publisher_cc: model.publisherCountryCode,
      purpose_consents: ids(model.purposeConsents),
      purpose_li: ids(model.purposeLegitimateInterests),
      special_feature_optins: ids(model.specialFeatureOptins),
      vendor_consents: ids(model.vendorConsents),
      vendor_li: ids(model.vendorLegitimateInterests),
      publisher_consents: ids(model.publisherConsents),
      publisher_li: ids(model.publisherLegitimateInterests),
      vendors_disclosed: ids(model.vendorsDisclosed),
    };
  } catch (error) {
    return { tc_string: tcString, error: String(error && error.message || error) };
  }
}

const lines = readFileSync(0, 'utf8').split('\n').map((line) => line.trim()).filter(Boolean);
for (const line of lines) process.stdout.write(JSON.stringify(decode(line)) + '\n');
