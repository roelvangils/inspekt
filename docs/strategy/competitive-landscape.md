# Competitive Landscape & Strategic Positioning

> Last updated: April 2026

Inspekt is building four novel AI-powered accessibility testing features ([#31][i31], [#32][i32], [#33][i33], [#34][i34]). This document maps the competitive landscape and identifies where Inspekt is genuinely novel.

---

## Summary

| Feature | Competition | Verdict |
|---------|------------|---------|
| [#31 Crawl & Scan][i31] — heuristic red-flag scoring for WCAG-EM audit sample selection | Nobody does this | **Uncharted** |
| [#32 Multi-modal Verify][i32] — OCR vs. accessible name, TTS+Whisper pronunciation, pixel-diff state comparison | Nobody does this (axe checks Label in Name from DOM only) | **Uncharted** |
| [#33 Journey Simulation][i33] — automated SR task-based navigation | Guidepup / AssistivLabs automate real SRs but don't auto-generate journeys | **Partial overlap** |
| [#34 Semantic X-Ray][i34] — AI vision: visual intent vs. HTML/ARIA implementation | **Evinced** does something similar internally | **Evinced is closest** |
| [#35 Snapshot Testing][i35] — accessibility regression detection across deploys | Happo.io does limited ARIA snapshots | **Largely uncharted** |
| [#36 Debt Estimator][i36] — effort-based prioritization and tracking | Nobody translates issues to developer-hours | **Uncharted** |

---

## The key competitor: Evinced

[Evinced](https://www.evinced.com) is the only company doing vision-based semantic analysis in production. They are the primary competitive reference point for the Semantic X-Ray feature.

### What they do

- Use computer vision to identify visual UI components (buttons, tables, forms) even when the HTML is semantically wrong
- Compare visual intent against DOM implementation to find issues automated checkers miss
- Claim 19x more critical issues detected than legacy tools
- Detect headings visually and verify DOM heading hierarchy
- Cluster related issues to reduce noise

### How they differ from Inspekt

| Aspect | Evinced | Inspekt (planned) |
|--------|---------|-------------------|
| **Positioning** | Automated violation detector for enterprise compliance | Auditor's inspection & understanding tool |
| **Presentation** | Violation reports (pass/fail) | Side-by-side X-ray (intent vs. implementation) |
| **Pricing** | Enterprise SaaS (opaque, sales-driven) | Open source / self-hosted |
| **Transparency** | Black box — detection logic is opaque | Transparent — shows what AI sees and why |
| **Scope** | Semantic analysis only | Semantic + multi-modal + auditory + sample selection |
| **Sample selection** | No | Yes (#31) |
| **OCR verification** | No | Yes (#32) |
| **TTS pronunciation** | No | Yes (#32) |
| **State pixel comparison** | No | Yes (#32) |
| **Journey simulation** | No | Yes (#33) |

**Takeaway:** Evinced serves enterprise compliance buyers. Inspekt serves accessibility auditors. The X-ray framing (showing the gap, not just flagging it) is differentiated. The other three features have zero overlap.

### References

- [Evinced Technology](https://www.evinced.com/technology)
- [Evinced AI Detection](https://www.evinced.com/ai/detection)
- [Evinced — A Matter of Semantics](https://www.evinced.com/blog/its-just-a-matter-of-semantics)
- [Marcy Sutton — Evinced Pushing Limits](https://marcysutton.com/evinced-automated-accessibility-testing/)

---

## Industry direction: AI + accessibility

The industry is moving toward vision-based and AI-powered accessibility testing, but nobody has shipped a coherent product combining crawl + multi-modal + semantic analysis.

### Deque (axe DevTools)

The market leader in automated accessibility testing is adding AI:

- "Advanced rules, AI, machine vision, and screenshots" for their Intelligent Guided Tests (IGTs)
- Object detection algorithm that "encodes information about relationships between objects"
- Combines visual classification with DOM semantics
- Partially shipped, partially roadmap (2025-2026)

Deque's approach layers AI on top of their existing rule-based engine. They're improving existing automated testing, not rethinking the testing model.

- [Advancing AI for axe](https://www.deque.com/blog/advancing-ai-for-axe-the-next-leap-in-digital-accessibility/)
- [People-First Computer Vision in axe DevTools](https://www.deque.com/blog/deques-people-first-approach-to-computer-vision-in-axe-devtools/)
- [Deque axe AI](https://www.deque.com/axe/ai/)

### Research & prototypes (not products)

| Project | What it is | Status |
|---------|-----------|--------|
| [Microsoft OmniParser](https://microsoft.github.io/OmniParser/) | Converts UI screenshots to structured DOM-like representations using vision + OCR + icon classification. [Blog post](https://devblogs.microsoft.com/semantic-kernel/guest-blog-letting-ai-help-make-the-world-more-accessible-analyzing-website-accessibility-with-semantic-kernel-and-omniparser/) demos using it with an LLM for accessibility analysis. | Open source, proof-of-concept |
| [Google ScreenAI](https://research.google/blog/screenai-a-visual-language-model-for-ui-and-visually-situated-language-understanding/) | 5B-parameter vision-language model trained on UI screenshots. SOTA on UI understanding tasks. | Research model, not a product |
| [GenA11y](https://dl.acm.org/doi/10.1145/3729371) (FSE 2025) | Multimodal generative AI for accessibility detection. 94.5% precision, 87.6% recall. Found 8 more violation types than existing tools combined. | Academic paper |

### Other AI-adjacent tools

| Tool | AI Features | Relevance |
|------|------------|-----------|
| [Applitools](https://applitools.com/platform/validate/accessibility/) | Visual AI contrast checking from screenshots, cross-browser comparison | Contrast only — doesn't check semantics |
| [Happo.io](https://happo.io/accessibility) | Visual regression + axe-core + ARIA snapshots in CI/CD | Visual regression, not semantic analysis |
| [AssistivLabs](https://assistivlabs.com/articles/automating-screen-readers-for-accessibility-testing) | Cloud-hosted real screen readers (JAWS, NVDA, VoiceOver) with machine vision | Closest to journey simulation, but managed service |
| [Guidepup](https://github.com/guidepup/aria-at-tests) | Open source VoiceOver/NVDA automation for CI/CD | Programmatic SR testing, doesn't auto-generate journeys |
| [Level Access](https://www.levelaccess.com/news/level-access-accelerates-investment-in-ai-innovation/) | AI agents for reporting, issue grouping, audit summaries | Workflow AI, not detection AI |
| [TestParty](https://testparty.ai/) | AI scanning + human remediation, GitHub PRs with fixes | Remediation-focused |
| [Stark](https://www.getstark.co/figma/) | AI alt text suggestions, vision simulation in Figma | Design-stage tool, not testing |
| [Silktide](https://silktide.com/solutions/accessibility/) | "Spectra" AI for faster detection, real-browser rendering | Site-wide monitoring |

---

## Traditional site-wide scanners

These are the established players in crawl-based accessibility scanning. None use AI for detection — they all run rule-based WCAG checks (axe-core, WAVE, or proprietary rulesets).

| Tool | Approach | Heuristic red flags? | Sample selection? |
|------|----------|---------------------|-------------------|
| [Screaming Frog](https://www.screamingfrog.co.uk/seo-spider/tutorials/how-to-perform-a-web-accessibility-audit/) + axe | Crawl + axe-core per page. Template segmentation. | No | No |
| [Sitebulb](https://sitebulb.com/product/accessibility/) | Crawl + accessibility hints. Closest to heuristic flagging. | Partially (still rule-based) | No |
| [Pope Tech](https://www.pope.tech/) | WAVE-based, dashboards, severity scoring | No | No |
| [Siteimprove](https://www.siteimprove.com/) | Scheduled crawls, PDF scanning, compliance dashboards | No | No |
| [Monsido](https://monsido.com/) | Similar to Siteimprove | No | No |
| [Accessibility Cloud](https://www.accessibilitycloud.com/) | WCAG-EM workflows, fast crawling (100k pages/hr) | No | No |

**Key gap:** All of these find WCAG violations on a per-page basis. None score pages by "suspiciousness" or help auditors select a representative sample per [WCAG-EM methodology](https://www.w3.org/WAI/test-evaluate/conformance/wcag-em/). This is exactly what [#31][i31] addresses.

---

## Where Inspekt is genuinely novel

### Things nobody does at all

1. **Heuristic red-flag scoring for audit sample selection** (#31) — crawl a site and rank pages by how "suspicious" they look (ARIA overuse, PDF downloads, carousels, "click here" links), producing a prioritized sample list for WCAG-EM audits
2. **OCR vs. accessible name comparison** (#32) — screenshot an element, run OCR on the rendered pixels, compare with the programmatic accessible name to catch visual/semantic mismatches
3. **TTS → Whisper pronunciation verification** (#32) — synthesize the accessible name with TTS, transcribe with speech recognition, compare to catch pronunciation issues (numbers, abbreviations, symbols)
4. **Visual state pixel comparison for accessibility** (#32) — screenshot hover/focus/active states, pixel-diff to verify they're distinguishable and meet WCAG 2.4.11 Focus Appearance

### Things one competitor does differently

5. **Semantic X-Ray** (#34) — Evinced does vision-based semantic analysis internally, but presents it as violation reports for enterprise compliance. Inspekt presents it as an auditor's tool showing intent vs. implementation side-by-side. The "X-ray" framing is novel.

### The overall vision is unique

No tool combines crawl-for-sampling + multi-modal element verification + semantic X-ray into a coherent pipeline. The four features form an audit workflow:

1. **Which pages need attention?** → Crawl & Scan (#31)
2. **Does the code match what the design meant?** → Semantic X-Ray (#34)
3. **Is each element truly accessible?** → Multi-modal Verify (#32)
4. **Can a real user complete tasks?** → Journey Simulation (#33)
5. **What changed since last time?** → Snapshot Testing (#35)
6. **How much work is it to fix?** → Debt Estimator (#36)

This mirrors the WCAG-EM evaluation methodology with tooling that doesn't exist anywhere else.

6. **Accessibility snapshot testing / regression detection** (#35) — like Percy/Chromatic for accessibility. Take an accessibility fingerprint, diff across deploys, catch regressions. Happo.io does a limited version (ARIA snapshots alongside visual snapshots) but nobody does it comprehensively.
7. **Accessibility debt estimation in developer-hours** (#36) — every tool gives you severity. Nobody translates issues into effort, groups by root cause/template, or produces sprint-ready remediation backlogs with time estimates.

---

## Overlay products (not competitors)

accessiBe, AudioEye, UserWay, and EqualWeb sell automated "overlay" widgets that claim to fix accessibility issues on the fly. These are widely criticized by the accessibility community, and AudioEye has been fined by the FTC. They are not relevant as competitors — they solve a different (arguably nonexistent) problem.

[i31]: https://github.com/roelvangils/inspekt/issues/31
[i32]: https://github.com/roelvangils/inspekt/issues/32
[i33]: https://github.com/roelvangils/inspekt/issues/33
[i34]: https://github.com/roelvangils/inspekt/issues/34
[i35]: https://github.com/roelvangils/inspekt/issues/35
[i36]: https://github.com/roelvangils/inspekt/issues/36
