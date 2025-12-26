/**
 * Alfa browser entry point for inspekt
 *
 * This exports what's needed for browser-based accessibility auditing.
 */

// Core auditing
export { Audit } from '@siteimprove/alfa-act';
export { Outcome } from '@siteimprove/alfa-act';

// DOM handling
export { Native } from '@siteimprove/alfa-dom/native';
export { Document, Element, Node } from '@siteimprove/alfa-dom';

// Device for viewport info
export { Device } from '@siteimprove/alfa-device';

// Page object (what rules expect as input)
export { Page } from '@siteimprove/alfa-web';

// HTTP types for creating Page
export { Request, Response } from '@siteimprove/alfa-http';

// URL type for parsing URLs
export { URL } from '@siteimprove/alfa-url';

// All rules - import as default for convenience
import FlattenedRules from '@siteimprove/alfa-rules';
export const Rules = FlattenedRules;

// For building Alfa documents from native JSON
import { Document as AlfaDocument } from '@siteimprove/alfa-dom';
import { Device as AlfaDevice } from '@siteimprove/alfa-device';
import { Native as AlfaNative } from '@siteimprove/alfa-dom/native';
import { Audit as AlfaAudit } from '@siteimprove/alfa-act';
import { Page as AlfaPage } from '@siteimprove/alfa-web';
import { Request as AlfaRequest, Response as AlfaResponse } from '@siteimprove/alfa-http';
import { URL as AlfaURL } from '@siteimprove/alfa-url';

/**
 * Run accessibility audit on current document
 * @returns Array of audit outcomes
 */
export async function runAudit(options = {}) {
  // Create device representing current viewport
  const device = AlfaDevice.standard();

  // Extract DOM from browser
  const nativeResult = await AlfaNative.fromNode(globalThis.document);

  // Convert to Alfa Document using fromDocument
  // Note: fromDocument returns a Trampoline that needs to be run
  const alfaDocTrampoline = AlfaDocument.fromDocument(nativeResult, device);
  const alfaDocument = alfaDocTrampoline.run();

  // Create mock Request/Response for the Page object
  // Parse URL string into Alfa URL object (required by Request/Response)
  const urlString = globalThis.location?.href || 'http://localhost/';
  const urlResult = AlfaURL.parse(urlString);

  // Handle URL parse failure gracefully
  if (!urlResult.isOk()) {
    throw new Error(`Failed to parse URL: ${urlString}`);
  }

  const alfaUrl = urlResult.getUnsafe();
  const request = AlfaRequest.of('GET', alfaUrl);
  const response = AlfaResponse.of(alfaUrl, 200);

  // Create Page object (what rules expect as input)
  const page = AlfaPage.of(request, response, alfaDocument, device);

  // Create audit with all rules
  const audit = AlfaAudit.of(page, FlattenedRules);

  // Run audit - returns a Future
  const outcomesFuture = audit.evaluate();

  // Convert Future to Promise and collect results
  const outcomes = await outcomesFuture.toPromise();

  // Convert to plain objects for serialization
  const results = [];
  for (const outcome of outcomes) {
    // Extract path from target element if available
    // This generates XPath-like paths: /html[1]/body[1]/div[2]
    let path = null;
    if (outcome.target && typeof outcome.target.path === 'function') {
      try {
        path = outcome.target.path();
      } catch (e) {
        // Path extraction may fail for some node types
      }
    }

    results.push({
      rule: outcome.rule.uri,
      outcome: outcome.outcome,
      target: outcome.target ? outcome.target.toString() : null,
      path: path,  // XPath for element resolution in browser
      // Include rule details for popover display
      ruleTitle: outcome.rule?.title || null,
      ruleRequirements: outcome.rule?.requirements?.map(r => r.toString()) || [],
    });
  }

  return results;
}
