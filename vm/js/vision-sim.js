// =============================================
// Vision Simulator for Inspekt VM
// =============================================
//
// Applies vision impairment simulations on the VNC canvas container.
// Filters are applied at the viewport level (CSS filter + mask on
// #vncContainer), so the actual page being tested is never modified.
//
// Dependencies (globals from control-panel.html):
//   - showToast()          (UI helper)
//   - SVG <defs> block with filter definitions (injected into the page)

// =============================================
// 1. Simulation Profiles
// =============================================
// Each profile defines how to simulate a vision condition.
// - svgFilter:   ID of an SVG filter defined in the page's <defs>
// - cssFilter:   Additional CSS filter string (blur, contrast, etc.)
// - mask:        CSS mask-image for spatial effects (tunnel vision)
// - description: Shown in the UI

const VISION_PROFILES = {
    // ---- Color Vision Deficiencies ----
    protanopia: {
        label: 'Protanopia',
        group: 'Color blindness',
        description: 'Red-blind — no red cones (~1% of males)',
        svgFilter: 'vision-protanopia'
    },
    deuteranopia: {
        label: 'Deuteranopia',
        group: 'Color blindness',
        description: 'Green-blind — no green cones (~1% of males)',
        svgFilter: 'vision-deuteranopia'
    },
    tritanopia: {
        label: 'Tritanopia',
        group: 'Color blindness',
        description: 'Blue-blind — no blue cones (very rare)',
        svgFilter: 'vision-tritanopia'
    },
    achromatopsia: {
        label: 'Achromatopsia',
        group: 'Color blindness',
        description: 'Total color blindness — rod monochromacy with photophobia',
        svgFilter: 'vision-achromatopsia',
        cssFilter: 'blur(0.8px)'
    },
    protanomaly: {
        label: 'Protanomaly',
        group: 'Color blindness',
        description: 'Red-weak — reduced red sensitivity (~1% of males)',
        svgFilter: 'vision-protanomaly'
    },
    deuteranomaly: {
        label: 'Deuteranomaly',
        group: 'Color blindness',
        description: 'Green-weak — reduced green sensitivity (~5% of males)',
        svgFilter: 'vision-deuteranomaly'
    },
    tritanomaly: {
        label: 'Tritanomaly',
        group: 'Color blindness',
        description: 'Blue-weak — reduced blue sensitivity (very rare)',
        svgFilter: 'vision-tritanomaly'
    },

    // ---- Acuity / Optical ----
    'low-vision-mild': {
        label: 'Low Vision (mild)',
        group: 'Acuity',
        description: 'Blurred vision — approx. 20/70 acuity',
        cssFilter: 'blur(1.5px)'
    },
    'low-vision-moderate': {
        label: 'Low Vision (moderate)',
        group: 'Acuity',
        description: 'Blurred vision — approx. 20/100 acuity',
        cssFilter: 'blur(3px)'
    },
    'low-vision-severe': {
        label: 'Low Vision (severe)',
        group: 'Acuity',
        description: 'Blurred vision — approx. 20/200 acuity',
        cssFilter: 'blur(6px)'
    },
    cataracts: {
        label: 'Cataracts',
        group: 'Acuity',
        description: 'Cloudy lens — blur, reduced contrast, yellowing',
        svgFilter: 'vision-cataracts',
        cssFilter: 'blur(1.5px)'
    },
    'reduced-contrast': {
        label: 'Reduced Contrast',
        group: 'Acuity',
        description: 'Low contrast sensitivity — washed-out appearance',
        cssFilter: 'contrast(0.55) brightness(1.1)'
    },

    // ---- Optical / Structural ----
    keratoconus: {
        label: 'Keratoconus',
        group: 'Optical',
        description: 'Corneal distortion — irregular warping and ghosting',
        svgFilter: 'vision-keratoconus',
        cssFilter: 'blur(0.5px)',
        // Animate the turbulence filter for a living, organic distortion
        animateFilter: {
            filterId: 'vision-keratoconus',
            baseFreq: [0.012, 0.015],  // center values for X and Y
            freqDrift: 0.003,          // ± drift range
            scaleDrift: 3,             // displacement scale ± drift (base 14)
            speed: 0.4                 // animation speed (radians/sec)
        }
    },
    metamorphopsia: {
        label: 'Metamorphopsia',
        group: 'Optical',
        description: 'Wavy distortion — straight lines appear bent (AMD)',
        svgFilter: 'vision-metamorphopsia',
        animateFilter: {
            filterId: 'vision-metamorphopsia',
            baseFreq: [0.006, 0.018],
            freqDrift: 0.002,
            scaleDrift: 2,             // base 10
            speed: 0.3
        }
    },
    diplopia: {
        label: 'Diplopia',
        group: 'Optical',
        description: 'Double vision — ghost image shifts with eye movement',
        svgFilter: 'vision-diplopia',
        // Mouse-reactive offset: ghost image moves opposite to gaze direction
        diplopiaTracking: {
            filterId: 'vision-diplopia',
            baseOffset: [4, 2],   // constant offset (px) even when mouse is centered
            sensitivity: 10,      // max additional offset (px) at canvas edges
            idleDelay: 1000,      // ms before idle drift kicks in
            driftRadius: 5,       // px radius of the circular drift
            driftSpeed: 0.35      // radians/sec
        }
    },
    'diabetic-floaters': {
        label: 'Diabetic Floaters',
        group: 'Optical',
        description: 'Dark blobs drifting across the visual field',
        floaters: true  // triggers the animated floater overlay system
    },
    'corneal-scarring': {
        label: 'Corneal Scarring',
        group: 'Optical',
        description: 'Localized blur and distortion from corneal damage',
        svgFilter: 'vision-corneal-scarring',
        // Static field layers (no mouse tracking — scar is fixed on the cornea)
        trackMouse: false,
        fieldLayers: [
            {
                blur: 14,
                background: 'none',
                maskFn: () => `radial-gradient(ellipse 18% 14% at 42% 38%, black 20%, rgba(0,0,0,0.5) 50%, rgba(0,0,0,0.15) 75%, transparent 100%)`
            },
            {
                blur: 0,
                background: 'rgba(0, 0, 0, 0.35)',
                maskFn: () => `radial-gradient(ellipse 12% 10% at 42% 38%, black 15%, rgba(0,0,0,0.3) 45%, transparent 80%)`
            }
        ]
    },

    // ---- Visual Field ----
    // Visual field simulations use TWO stacked overlay layers:
    //
    //   1. Blur layer — wide mask, gentle feathering, backdrop-filter: blur().
    //      No background color. Creates a large zone of progressive defocus.
    //
    //   2. Dark layer — tighter mask, background: black, no blur.
    //      Adds blackout only at the far edges.
    //
    // The zone between the two masks (blurry but still visible) is what makes
    // the effect feel like real peripheral vision loss instead of a spotlight.
    // In real RP, you lose sharpness first, then brightness — the blur zone
    // is much wider than the dark zone.
    //
    // Each maskFn receives (x%, y%) and returns a mask-image string.
    'tunnel-vision': {
        label: 'Tunnel Vision',
        group: 'Visual field',
        description: 'Peripheral vision loss (retinitis pigmentosa)',
        fieldLayers: [
            {
                // Blur layer — starts close to center, extends very wide
                blur: 16,
                background: 'none',
                maskFn: (x, y) => `radial-gradient(circle at ${x} ${y}, transparent 6%, rgba(0,0,0,0.08) 10%, rgba(0,0,0,0.2) 16%, rgba(0,0,0,0.45) 26%, rgba(0,0,0,0.7) 38%, black 60%)`
            },
            {
                // Dark layer — kicks in further out, tighter gradient
                blur: 0,
                background: 'rgba(0, 0, 0, 0.85)',
                maskFn: (x, y) => `radial-gradient(circle at ${x} ${y}, transparent 18%, rgba(0,0,0,0.1) 25%, rgba(0,0,0,0.4) 38%, rgba(0,0,0,0.75) 52%, black 72%)`
            }
        ]
    },
    'central-scotoma': {
        label: 'Central Scotoma',
        group: 'Visual field',
        description: 'Central vision loss (macular degeneration)',
        fieldLayers: [
            {
                // Blur layer — central blur spot
                blur: 18,
                background: 'none',
                maskFn: (x, y) => `radial-gradient(circle at ${x} ${y}, black 0%, rgba(0,0,0,0.7) 5%, rgba(0,0,0,0.3) 12%, transparent 22%)`
            },
            {
                // Dark layer — dense core only
                blur: 0,
                background: 'rgba(0, 0, 0, 0.6)',
                maskFn: (x, y) => `radial-gradient(circle at ${x} ${y}, black 0%, rgba(0,0,0,0.6) 4%, rgba(0,0,0,0.2) 9%, transparent 16%)`
            }
        ]
    }
};


// =============================================
// 1b. Info Content (for the HUD info overlay)
// =============================================

const VISION_INFO = {
    protanopia: {
        medicalName: 'Protanopia',
        category: 'Color Vision Deficiency',
        description: 'Complete absence of red-sensitive cone cells (L-cones) in the retina. Colors are perceived using only green (M) and blue (S) cones. Reds appear dark, and red-green distinctions are lost entirely.',
        prevalence: 'Affects approximately 1% of males and 0.01% of females. It is inherited as an X-linked recessive trait.',
        impact: 'Red text on dark backgrounds can become invisible. Status indicators that rely solely on red/green color (error vs. success) are ambiguous. Color-coded charts and maps lose meaning. Links distinguished only by color from surrounding text cannot be identified.'
    },
    deuteranopia: {
        medicalName: 'Deuteranopia',
        category: 'Color Vision Deficiency',
        description: 'Complete absence of green-sensitive cone cells (M-cones). This is the most common form of dichromacy. Similar to protanopia in that red-green distinctions are lost, but reds do not appear as dark.',
        prevalence: 'Affects approximately 1% of males. Together with deuteranomaly, green-deficient conditions affect about 6% of all males.',
        impact: 'Green indicators (success states, "go" signals) blend with reds and browns. Syntax highlighting in code editors loses contrast between keywords. Navigation elements that use green to indicate the current page become invisible.'
    },
    tritanopia: {
        medicalName: 'Tritanopia',
        category: 'Color Vision Deficiency',
        description: 'Complete absence of blue-sensitive cone cells (S-cones). Blue-yellow distinctions are lost. Unlike red-green deficiencies, tritanopia is not sex-linked and affects males and females equally.',
        prevalence: 'Extremely rare — affects fewer than 0.01% of the population. Can also be acquired through aging or retinal disease.',
        impact: 'Blue links on white backgrounds may appear indistinguishable from black text. Blue-yellow data visualizations lose all meaning. Warning indicators using yellow may be confused with light or neutral colors.'
    },
    achromatopsia: {
        medicalName: 'Achromatopsia (Rod Monochromacy)',
        category: 'Color Vision Deficiency',
        description: 'Complete absence of functional cone cells. Vision relies entirely on rod cells, which detect only luminance (brightness) and not color. Accompanied by severe light sensitivity (photophobia), reduced visual acuity (typically 20/200), and nystagmus.',
        prevalence: 'Affects approximately 1 in 30,000 to 50,000 people worldwide. Higher prevalence in certain Pacific island populations (up to 10% in Pingelap atoll).',
        impact: 'All color information is lost — UI must communicate through shape, position, size, and text. Bright white backgrounds cause pain and washout; dark mode is essential. Text must have high contrast against its background to be readable with reduced acuity.'
    },
    protanomaly: {
        medicalName: 'Protanomaly',
        category: 'Color Vision Deficiency',
        description: 'Red-sensitive cones (L-cones) are present but have shifted spectral sensitivity, making them respond more like green cones. Red-green discrimination is weakened but not eliminated.',
        prevalence: 'Affects approximately 1% of males. The most common form of protan (red-deficient) color vision.',
        impact: 'Subtle color differences between reds, oranges, and greens are lost. Error messages in soft red may not stand out from neutral text. Color-only hover states and focus indicators can be missed.'
    },
    deuteranomaly: {
        medicalName: 'Deuteranomaly',
        category: 'Color Vision Deficiency',
        description: 'Green-sensitive cones (M-cones) have shifted spectral sensitivity. This is the single most common color vision deficiency. Most people with this condition are unaware of it.',
        prevalence: 'Affects approximately 5% of males and 0.35% of females — the most common CVD by far. About 1 in 12 males of Northern European descent.',
        impact: 'Greens and reds can appear similar, especially in small or thin elements (icons, border colors, underlines). Color-coded status badges may all look the same. Charts with green and red data series are difficult to read.'
    },
    tritanomaly: {
        medicalName: 'Tritanomaly',
        category: 'Color Vision Deficiency',
        description: 'Blue-sensitive cones (S-cones) have shifted spectral sensitivity, weakening blue-yellow discrimination. Often acquired later in life rather than inherited.',
        prevalence: 'Very rare as a congenital condition (< 0.01%). More commonly acquired through aging, diabetes, or medication side effects.',
        impact: 'Blue interface elements may appear greenish. Yellow warning states can appear pinkish or light grey. Subtle distinctions between blues, purples, and greens are lost.'
    },
    'low-vision-mild': {
        medicalName: 'Mild Low Vision',
        category: 'Visual Acuity',
        description: 'Reduced ability to resolve fine detail, equivalent to approximately 20/70 visual acuity. Cannot be fully corrected with glasses or contact lenses. Many causes including early-stage macular degeneration, diabetic retinopathy, or mild corneal issues.',
        prevalence: 'An estimated 246 million people worldwide have moderate to severe vision impairment. Low vision affects about 3% of people over 40.',
        impact: 'Small text (under 14px) becomes difficult to read. Fine UI details like thin borders, subtle icons, and small interactive targets are harder to perceive. Users often rely on browser zoom (125-150%).'
    },
    'low-vision-moderate': {
        medicalName: 'Moderate Low Vision',
        category: 'Visual Acuity',
        description: 'Significant reduction in visual acuity, approximately 20/100. Reading standard text requires magnification. Faces are difficult to recognize at conversational distance.',
        prevalence: 'Included in the 246 million estimate for moderate-severe vision impairment globally. Prevalence increases significantly with age.',
        impact: 'Standard-sized web text is unreadable without zoom or screen magnification. Navigation depends on large, high-contrast elements. Icon-only buttons without labels become unusable. Touch targets must be significantly larger than standard (at least 44×44px).'
    },
    'low-vision-severe': {
        medicalName: 'Severe Low Vision',
        category: 'Visual Acuity',
        description: 'Profound reduction in visual acuity, approximately 20/200 — the threshold for "legal blindness" in many countries. Only large, high-contrast shapes are distinguishable.',
        prevalence: 'Approximately 43 million people worldwide are blind or have severe vision impairment.',
        impact: 'Users typically rely on screen magnification software (ZoomText, built-in OS zoom) at 200-400%. Only a small portion of the page is visible at a time. Navigation becomes sequential — users scan the page section by section. Screen readers may be used in combination with magnification.'
    },
    cataracts: {
        medicalName: 'Cataracts',
        category: 'Visual Acuity',
        description: 'Clouding of the eye\'s natural lens, causing blurred vision, reduced contrast sensitivity, and a yellow-brown tint. The most common cause of reversible vision loss worldwide. Develops gradually with age.',
        prevalence: 'Affects over 50% of people over age 80. Approximately 94 million people worldwide have vision impairment from cataracts.',
        impact: 'Text appears blurry and low-contrast. White backgrounds may cause glare. Colors appear warmer/yellowed, shifting the perception of UI color schemes. Fine typography and thin fonts become unreadable. Dark mode significantly improves usability.'
    },
    'reduced-contrast': {
        medicalName: 'Reduced Contrast Sensitivity',
        category: 'Visual Acuity',
        description: 'Difficulty distinguishing between elements of similar brightness, even when visual acuity is otherwise normal. Common in glaucoma, cataracts, diabetic retinopathy, and normal aging.',
        prevalence: 'Contrast sensitivity declines in nearly everyone over age 50. Clinically significant reduction affects an estimated 5-10% of adults over 65.',
        impact: 'Light grey text on white backgrounds becomes invisible. Subtle hover and focus states are missed entirely. Placeholder text in form fields cannot be read. Low-contrast borders between sections disappear, making page structure unclear. WCAG contrast ratios exist specifically for this condition.'
    },
    keratoconus: {
        medicalName: 'Keratoconus',
        category: 'Optical / Structural',
        description: 'Progressive thinning and bulging of the cornea into a cone shape, causing irregular astigmatism. The cornea\'s uneven surface distorts light entering the eye, producing warped, ghosted, and streaked vision that cannot be fully corrected with standard glasses.',
        prevalence: 'Affects approximately 1 in 2,000 people. Usually develops in the teens or early 20s and may progress until the mid-30s. More common than previously thought — recent studies suggest prevalence may be as high as 1 in 375.',
        impact: 'Text appears ghosted or doubled at certain angles. Fine details like small icons and thin fonts are smeared. High-contrast edges (dark text on white) may show streaking or halos. UI elements with precise alignment requirements (grids, tables) appear distorted and misaligned.'
    },
    metamorphopsia: {
        medicalName: 'Metamorphopsia',
        category: 'Optical / Structural',
        description: 'A visual distortion where straight lines appear wavy, bent, or irregular. Most commonly caused by macular conditions — particularly wet age-related macular degeneration (AMD), epiretinal membrane, or macular edema — where fluid or tissue growth distorts the photoreceptor arrangement.',
        prevalence: 'Present in the majority of people with wet AMD (affecting ~20 million worldwide). Also common in diabetic macular edema and epiretinal membrane. Prevalence increases significantly with age.',
        impact: 'Grid layouts, tables, and aligned text columns appear wavy and misaligned. Reading becomes fatiguing because letters appear to shift and bend. Navigation menus and toolbars look distorted. The Amsler grid test (a grid of straight lines) is the clinical screening tool — patients see the lines as wavy or broken.'
    },
    diplopia: {
        medicalName: 'Diplopia (Double Vision)',
        category: 'Optical / Structural',
        description: 'Seeing two overlapping images of a single object. Can be monocular (one eye) or binocular (both eyes). Binocular diplopia is caused by misalignment of the eyes (strabismus), while monocular diplopia can result from cataracts, keratoconus, or corneal irregularities. The ghost image typically shifts with eye movement.',
        prevalence: 'Affects approximately 850,000 people in the US alone. Binocular diplopia has an annual incidence of about 5 per 100,000. More common in people over 60, those with diabetes, or after head trauma.',
        impact: 'Text appears doubled and overlapping, making reading extremely difficult. UI elements seem to have a ghost copy offset to one side. Users may close one eye to eliminate the doubling. Precise mouse targeting becomes harder because the perceived position doesn\'t match the real position. High-contrast edges (text, borders, icons) show the doubling most prominently.'
    },
    'diabetic-floaters': {
        medicalName: 'Vitreous Floaters (Diabetic Retinopathy)',
        category: 'Optical / Structural',
        description: 'Dark spots, cobwebs, or cloud-like shapes that drift across the visual field. Caused by clumps of cells or protein in the vitreous humor (the gel filling the eye). In diabetic retinopathy, abnormal blood vessels may leak blood into the vitreous, creating larger and more numerous floaters.',
        prevalence: 'Mild floaters affect up to 70% of people over age 60. Diabetic retinopathy — the leading cause of severe floaters in working-age adults — affects approximately 100 million people worldwide. About 1 in 3 people with diabetes develop some form of retinopathy.',
        impact: 'Dark patches intermittently obscure parts of the screen as the eye moves. Reading requires extra effort as floaters drift across text. Small UI elements (icons, close buttons, checkboxes) can be temporarily hidden. The effect is worse on bright backgrounds (white pages, light mode). Users may need to pause and wait for floaters to drift out of their central vision.'
    },
    'corneal-scarring': {
        medicalName: 'Corneal Scarring (Corneal Opacity)',
        category: 'Optical / Structural',
        description: 'Permanent clouding or opacification of the cornea from injury, infection, surgery, or disease. The scar scatters light passing through it, creating a localized patch of blurred and distorted vision. Unlike conditions that affect the retina, corneal scars stay in a fixed position relative to the pupil.',
        prevalence: 'Corneal opacity is the fourth leading cause of blindness globally, affecting approximately 6 million people. Causes include trachoma (infectious), chemical burns, herpes keratitis, and surgical complications.',
        impact: 'A persistent blurry patch partially obscures the screen — like looking through a smudged window. The patch does not move with eye movement (it stays on the cornea). Content behind the scar is distorted and low-contrast. Users learn to position content outside the scarred area by scrolling or repositioning their head.'
    },
    'tunnel-vision': {
        medicalName: 'Tunnel Vision (Peripheral Vision Loss)',
        category: 'Visual Field Loss',
        description: 'Severe loss of peripheral vision while central vision remains intact. The visual field is reduced to a narrow cone, like looking through a tube. Most commonly caused by retinitis pigmentosa (RP), advanced glaucoma, or stroke.',
        prevalence: 'Retinitis pigmentosa alone affects approximately 1 in 4,000 people. Glaucoma-related peripheral loss affects over 70 million people worldwide.',
        impact: 'Users can only see a small area of the screen at once. Navigation menus at screen edges may be completely invisible. Pop-up dialogs appearing outside the current focus area are missed. Users must physically scan the entire page by moving their eyes systematically. Fixed-position elements (sticky headers, floating buttons) can obstruct the limited visible area.'
    },
    'central-scotoma': {
        medicalName: 'Central Scotoma',
        category: 'Visual Field Loss',
        description: 'A blind or blurred spot in the center of the visual field, where detailed vision normally occurs. Peripheral vision remains intact. Most commonly caused by age-related macular degeneration (AMD), which damages the macula — the part of the retina responsible for sharp central vision.',
        prevalence: 'AMD is the leading cause of vision loss in people over 50 in developed countries, affecting approximately 196 million people worldwide. About 10% of people over 65 have some degree of central vision loss.',
        impact: 'Users cannot see what they are directly looking at — they must use peripheral vision and "eccentric viewing" (looking slightly off-center). Reading text is extremely difficult. Small interactive targets (icons, close buttons) directly under the cursor are invisible. Users benefit from larger text, generous spacing, and the ability to reflow content.'
    }
};


// =============================================
// 2. SVG Filter Definitions
// =============================================
// Injected once into the page. Uses feColorMatrix with Machado et al. (2009)
// matrices for color blindness simulation in linearRGB color space.

const VISION_SVG_FILTERS = `
<svg xmlns="http://www.w3.org/2000/svg" style="position:absolute;width:0;height:0;" aria-hidden="true">
  <defs>
    <!-- Protanopia (red-blind) -->
    <filter id="vision-protanopia" color-interpolation-filters="linearRGB">
      <feColorMatrix type="matrix" values="
        0.567 0.433 0     0 0
        0.558 0.442 0     0 0
        0     0.242 0.758 0 0
        0     0     0     1 0"/>
    </filter>

    <!-- Deuteranopia (green-blind) — Chrome/Blink precise values -->
    <filter id="vision-deuteranopia" color-interpolation-filters="linearRGB">
      <feColorMatrix type="matrix" values="
        0.367  0.861 -0.228 0 0
        0.280  0.673  0.047 0 0
       -0.012  0.043  0.969 0 0
        0      0      0     1 0"/>
    </filter>

    <!-- Tritanopia (blue-blind) -->
    <filter id="vision-tritanopia" color-interpolation-filters="linearRGB">
      <feColorMatrix type="matrix" values="
        0.95 0.05  0     0 0
        0    0.433 0.567 0 0
        0    0.475 0.525 0 0
        0    0     0     1 0"/>
    </filter>

    <!-- Achromatopsia (rod monochromacy) —
         1. Desaturate to greyscale (rod-only, no cone response)
         2. Photophobia: bright areas wash out while darks stay dark.
            Uses a gamma curve (exponent < 1) which lifts midtones and highlights
            more than shadows, simulating how bright light overwhelms rod cells.
         3. Bloom: bright areas bleed light into surroundings. -->
    <filter id="vision-achromatopsia" color-interpolation-filters="linearRGB">
      <!-- Step 1: Desaturate to luminance -->
      <feColorMatrix type="matrix" values="
        0.299 0.587 0.114 0 0
        0.299 0.587 0.114 0 0
        0.299 0.587 0.114 0 0
        0     0     0     1 0" result="grey"/>
      <!-- Step 2: Photophobia — gamma < 1 lifts highlights disproportionately. -->
      <feComponentTransfer in="grey" result="photo">
        <feFuncR type="gamma" amplitude="1" exponent="0.6" offset="0"/>
        <feFuncG type="gamma" amplitude="1" exponent="0.6" offset="0"/>
        <feFuncB type="gamma" amplitude="1" exponent="0.6" offset="0"/>
      </feComponentTransfer>
      <!-- Step 3: Bloom — extract brights, blur, blend back. -->
      <feComponentTransfer in="photo" result="brights">
        <feFuncR type="linear" slope="1" intercept="-0.6"/>
        <feFuncG type="linear" slope="1" intercept="-0.6"/>
        <feFuncB type="linear" slope="1" intercept="-0.6"/>
      </feComponentTransfer>
      <feGaussianBlur in="brights" stdDeviation="4" result="glow"/>
      <feBlend in="photo" in2="glow" mode="screen"/>
    </filter>

    <!-- Protanomaly (red-weak) -->
    <filter id="vision-protanomaly" color-interpolation-filters="linearRGB">
      <feColorMatrix type="matrix" values="
        0.817 0.183 0     0 0
        0.333 0.667 0     0 0
        0     0.125 0.875 0 0
        0     0     0     1 0"/>
    </filter>

    <!-- Deuteranomaly (green-weak) -->
    <filter id="vision-deuteranomaly" color-interpolation-filters="linearRGB">
      <feColorMatrix type="matrix" values="
        0.8   0.2   0     0 0
        0.258 0.742 0     0 0
        0     0.142 0.858 0 0
        0     0     0     1 0"/>
    </filter>

    <!-- Tritanomaly (blue-weak) -->
    <filter id="vision-tritanomaly" color-interpolation-filters="linearRGB">
      <feColorMatrix type="matrix" values="
        0.967 0.033 0     0 0
        0     0.733 0.267 0 0
        0     0.183 0.817 0 0
        0     0     0     1 0"/>
    </filter>

    <!-- Keratoconus — irregular corneal distortion.
         feTurbulence generates organic Perlin noise; feDisplacementMap uses it
         to warp each pixel. scale=14 gives moderate distortion. -->
    <filter id="vision-keratoconus" color-interpolation-filters="sRGB">
      <feTurbulence type="turbulence" baseFrequency="0.012 0.015" numOctaves="3" seed="3" result="warp"/>
      <feGaussianBlur in="warp" stdDeviation="2" result="smoothWarp"/>
      <feDisplacementMap in="SourceGraphic" in2="smoothWarp" scale="14" xChannelSelector="R" yChannelSelector="G"/>
    </filter>

    <!-- Metamorphopsia — wavy distortion of straight lines.
         Lower frequency + fewer octaves = smoother, wave-like bends.
         The turbulence is blurred before displacement to create soft, flowing
         waves instead of harsh pixel-level warping. This also allows cheaper
         animation: the blurred displacement map hides transitions when
         baseFrequency changes. -->
    <filter id="vision-metamorphopsia" color-interpolation-filters="sRGB">
      <feTurbulence type="turbulence" baseFrequency="0.006 0.018" numOctaves="2" seed="7" result="wave"/>
      <feGaussianBlur in="wave" stdDeviation="3" result="smoothWave"/>
      <feDisplacementMap in="SourceGraphic" in2="smoothWave" scale="10" xChannelSelector="R" yChannelSelector="G"/>
    </filter>

    <!-- Diplopia (double vision) — splits the image into two copies offset
         in opposite directions, each at 50% opacity. Together they blend to
         roughly full brightness. Both feOffset elements are updated by JS on
         mousemove: copy A shifts with gaze, copy B shifts against it. -->
    <filter id="vision-diplopia" color-interpolation-filters="sRGB">
      <!-- Copy A: offset in one direction -->
      <feOffset in="SourceGraphic" dx="2" dy="1" result="copyA"/>
      <feComponentTransfer in="copyA" result="copyAFaded">
        <feFuncA type="linear" slope="0.5" intercept="0"/>
      </feComponentTransfer>
      <!-- Copy B: offset in the opposite direction -->
      <feOffset in="SourceGraphic" dx="-2" dy="-1" result="copyB"/>
      <feComponentTransfer in="copyB" result="copyBFaded">
        <feFuncA type="linear" slope="0.5" intercept="0"/>
      </feComponentTransfer>
      <!-- Blend both copies additively -->
      <feBlend in="copyAFaded" in2="copyBFaded" mode="screen"/>
    </filter>

    <!-- Corneal scarring — mild overall distortion (the localized blur is
         handled by a fieldLayers overlay, not this filter). -->
    <filter id="vision-corneal-scarring" color-interpolation-filters="sRGB">
      <feTurbulence type="turbulence" baseFrequency="0.02" numOctaves="2" seed="11" result="scar"/>
      <feDisplacementMap in="SourceGraphic" in2="scar" scale="6" xChannelSelector="R" yChannelSelector="G"/>
    </filter>

    <!-- Cataracts — yellowing + desaturation (blur added via CSS) -->
    <filter id="vision-cataracts" color-interpolation-filters="linearRGB">
      <feColorMatrix type="saturate" values="0.7"/>
      <feComponentTransfer>
        <feFuncR type="linear" slope="0.95" intercept="0.02"/>
        <feFuncG type="linear" slope="0.88" intercept="0.02"/>
        <feFuncB type="linear" slope="0.72" intercept="0.01"/>
      </feComponentTransfer>
    </filter>
  </defs>
</svg>`;


// =============================================
// 3. State
// =============================================

let _activeVisionProfile = null;
let _visionMouseTracker = null;
let _visionOverlays = [];  // Array of overlay elements (blur layer + dark layer)
let _floaterContainer = null; // Container for animated floater blobs
let _filterAnimationTimer = null; // Interval for animated SVG filter parameters
let _diplopiaTracker = null; // Mousemove handler for diplopia offset
let _simulationPaused = false;
let _hudElement = null;
let _infoOverlayElement = null;


// =============================================
// 4. Apply / Remove Simulation
// =============================================

function setVisionSimulation(profileId) {
    const container = document.getElementById('vncContainer');
    if (!container) return;

    // Clear previous simulation
    clearVisionSimulation();

    if (!profileId || profileId === 'none') {
        _activeVisionProfile = null;
        return;
    }

    const profile = VISION_PROFILES[profileId];
    if (!profile) return;

    _activeVisionProfile = profileId;
    _simulationPaused = false;

    _applyFilters(container, profile);

    // Update toolbar button state
    _updateVisionButtonState();
    _updateSimulatorHUD();

    showToast(`Vision: ${profile.label}`, 'info');
}

function clearVisionSimulation() {
    const container = document.getElementById('vncContainer');
    if (!container) return;

    // Remove CSS filters from the canvas (not the container — overlays must stay unfiltered)
    container.classList.remove('vision-filter-active');
    container.style.removeProperty('--vision-filter');

    // Remove visual field overlays, floaters, filter animation, and diplopia tracking
    _removeFieldOverlays();
    _removeFloaters();
    _stopFilterAnimation();
    _stopDiplopiaTracking();
    _stopMouseTracking();

    _activeVisionProfile = null;
    _simulationPaused = false;
    _updateVisionButtonState();
    _updateSimulatorHUD();
    _closeInfoOverlay();
}

function toggleVisionSimulation(profileId) {
    if (_activeVisionProfile === profileId) {
        clearVisionSimulation();
        showToast('Vision simulation off', 'info');
    } else {
        setVisionSimulation(profileId);
    }
}

/**
 * Apply CSS/SVG filters and overlay from a profile.
 * Filters are applied to the CANVAS only (via CSS custom property + class on
 * the container), not to the container itself. This ensures overlays like the
 * SR focus indicator, custom scrollbar, inspekt outlines, and the HUD pill
 * are never affected by the simulation filter.
 */
function _applyFilters(container, profile) {
    // Build CSS filter chain
    const filters = [];
    if (profile.svgFilter) {
        filters.push(`url(#${profile.svgFilter})`);
    }
    if (profile.cssFilter) {
        filters.push(profile.cssFilter);
    }
    if (filters.length > 0) {
        container.style.setProperty('--vision-filter', filters.join(' '));
        container.classList.add('vision-filter-active');
    }

    // Visual field simulations use stacked overlay layers
    if (profile.fieldLayers) {
        _createFieldOverlays(container, profile);
    }

    // Animated floater overlays (diabetic retinopathy)
    if (profile.floaters) {
        _createFloaters(container);
    }

    // Animated SVG filter parameters (keratoconus, metamorphopsia)
    if (profile.animateFilter) {
        _startFilterAnimation(profile.animateFilter);
    }

    // Diplopia mouse-reactive offset
    if (profile.diplopiaTracking) {
        _startDiplopiaTracking(container, profile.diplopiaTracking);
    }
}


// =============================================
// 5. Visual Field Overlays (stacked blur + dark layers)
// =============================================

function _createFieldOverlays(container, profile) {
    _removeFieldOverlays();

    for (const layer of profile.fieldLayers) {
        const el = document.createElement('div');
        el.className = 'vision-field-overlay';

        if (layer.blur > 0) {
            el.style.backdropFilter = `blur(${layer.blur}px)`;
            el.style.webkitBackdropFilter = `blur(${layer.blur}px)`;
        }
        if (layer.background && layer.background !== 'none') {
            el.style.background = layer.background;
        }

        // Set initial mask centered
        const initialMask = layer.maskFn('50%', '50%');
        el.style.webkitMaskImage = initialMask;
        el.style.maskImage = initialMask;

        // Store the maskFn on the element so mouse tracking can update it
        el._maskFn = layer.maskFn;

        container.appendChild(el);
        _visionOverlays.push(el);
    }

    // Start mouse tracking to move all layer masks (unless profile says not to)
    if (profile.trackMouse !== false) {
        _startMouseTracking(container);
    }
}

function _removeFieldOverlays() {
    for (const el of _visionOverlays) {
        el.remove();
    }
    _visionOverlays = [];
}


// =============================================
// 5b. Animated Floaters (diabetic retinopathy)
// =============================================
// Dark blurred blobs that drift slowly across the viewport using CSS animation.
// Each floater is a div with a radial-gradient background and blur filter.

const _FLOATER_CONFIGS = [
    { size: 90,  x: 25, y: 30, dur: 18, delay: 0,   opacity: 0.45, blur: 8  },
    { size: 55,  x: 60, y: 20, dur: 22, delay: -5,  opacity: 0.35, blur: 6  },
    { size: 120, x: 40, y: 55, dur: 25, delay: -10, opacity: 0.3,  blur: 12 },
    { size: 35,  x: 70, y: 65, dur: 15, delay: -3,  opacity: 0.5,  blur: 5  },
    { size: 70,  x: 15, y: 70, dur: 20, delay: -8,  opacity: 0.4,  blur: 7  },
    { size: 45,  x: 80, y: 40, dur: 17, delay: -12, opacity: 0.35, blur: 6  },
    { size: 25,  x: 50, y: 15, dur: 14, delay: -2,  opacity: 0.55, blur: 4  },
];

function _createFloaters(container) {
    _removeFloaters();

    const wrap = document.createElement('div');
    wrap.id = 'visionFloaters';
    wrap.className = 'vision-floaters';
    wrap.setAttribute('aria-hidden', 'true');

    for (const cfg of _FLOATER_CONFIGS) {
        const blob = document.createElement('div');
        blob.className = 'vision-floater';
        blob.style.width = cfg.size + 'px';
        blob.style.height = cfg.size + 'px';
        blob.style.left = cfg.x + '%';
        blob.style.top = cfg.y + '%';
        blob.style.opacity = cfg.opacity;
        blob.style.filter = `blur(${cfg.blur}px)`;
        blob.style.animationDuration = cfg.dur + 's';
        blob.style.animationDelay = cfg.delay + 's';
        wrap.appendChild(blob);
    }

    container.appendChild(wrap);
    _floaterContainer = wrap;
}

function _removeFloaters() {
    if (_floaterContainer) {
        _floaterContainer.remove();
        _floaterContainer = null;
    }
}


// =============================================
// 5c. Animated SVG Filter Parameters
// =============================================
// For keratoconus and metamorphopsia, slowly drift the turbulence
// baseFrequency and displacement scale to create a living distortion.
// Runs at ~15fps to avoid GPU pressure from recomputing feTurbulence.

function _startFilterAnimation(config) {
    _stopFilterAnimation();

    const filterEl = document.getElementById(config.filterId);
    if (!filterEl) return;

    const turbulence = filterEl.querySelector('feTurbulence');
    const displacement = filterEl.querySelector('feDisplacementMap');
    if (!turbulence || !displacement) return;

    const originalScale = parseFloat(displacement.getAttribute('scale')) || 10;
    const startTime = performance.now();

    // Fast loop (30fps): animate displacement scale only.
    // This is cheap — the browser reuses the cached turbulence texture
    // and just multiplies displacement values by the new scale.
    const scaleTimer = setInterval(() => {
        const t = (performance.now() - startTime) / 1000;
        const newScale = originalScale + config.scaleDrift * Math.sin(t * config.speed * 0.8 + 2.0);
        displacement.setAttribute('scale', newScale.toFixed(1));
    }, 33); // ~30fps

    // Slow loop (every 2s): animate baseFrequency.
    // This is expensive (regenerates the turbulence texture) but the blur
    // on the displacement map hides the transition, making it look smooth.
    const freqTimer = setInterval(() => {
        const t = (performance.now() - startTime) / 1000;
        const fx = config.baseFreq[0] + config.freqDrift * Math.sin(t * config.speed);
        const fy = config.baseFreq[1] + config.freqDrift * Math.cos(t * config.speed * 0.7 + 1.0);
        turbulence.setAttribute('baseFrequency', `${fx.toFixed(4)} ${fy.toFixed(4)}`);
    }, 2000); // every 2 seconds

    _filterAnimationTimer = { scaleTimer, freqTimer };
}

function _stopFilterAnimation() {
    if (_filterAnimationTimer) {
        clearInterval(_filterAnimationTimer.scaleTimer);
        clearInterval(_filterAnimationTimer.freqTimer);
        _filterAnimationTimer = null;
    }
}


// =============================================
// 5d. Diplopia Mouse Tracking + Idle Drift
// =============================================
// Three states:
//   1. Mouse moving → offset follows mouse (opposite direction)
//   2. Mouse idle < 1s → images realign toward center (smooth ease)
//   3. Mouse idle > 1s → slow circular drift (eyes trying to focus)

let _diplopiaIdleTimer = null;
let _diplopiaAnimFrame = null;
let _diplopia = null; // stores offsets, config, and current state

function _startDiplopiaTracking(container, config) {
    _stopDiplopiaTracking();

    const filterEl = document.getElementById(config.filterId);
    if (!filterEl) return;
    const offsets = filterEl.querySelectorAll('feOffset');
    if (offsets.length < 2) return;

    // State object shared between mousemove and animation loop
    _diplopia = {
        offsets,
        config,
        // Current offset (smoothed) — starts at base
        currentDx: config.baseOffset[0],
        currentDy: config.baseOffset[1],
        // Target offset from mouse (set on mousemove)
        targetDx: config.baseOffset[0],
        targetDy: config.baseOffset[1],
        // Idle drift state
        idle: false,
        idleStartTime: 0
    };

    // Mouse handler: set target and reset idle timer
    _diplopiaTracker = (e) => {
        const rect = container.getBoundingClientRect();
        const mx = ((e.clientX - rect.left) / rect.width - 0.5) * 2;
        const my = ((e.clientY - rect.top) / rect.height - 0.5) * 2;
        _diplopia.targetDx = config.baseOffset[0] + mx * config.sensitivity;
        _diplopia.targetDy = config.baseOffset[1] + my * config.sensitivity;
        _diplopia.idle = false;

        // Reset idle timer
        clearTimeout(_diplopiaIdleTimer);
        _diplopiaIdleTimer = setTimeout(() => {
            _diplopia.idle = true;
            _diplopia.idleStartTime = performance.now();
        }, config.idleDelay);
    };
    container.addEventListener('mousemove', _diplopiaTracker, true);

    // Animation loop: smoothly interpolate current toward target,
    // and add circular drift when idle
    const animate = () => {
        const d = _diplopia;
        if (!d) return;

        let dx, dy;

        if (d.idle) {
            const t = (performance.now() - d.idleStartTime) / 1000;
            // Phase 1 (0-1s): ease toward zero offset (realign)
            const realignProgress = Math.min(t, 1);
            const eased = 1 - Math.pow(1 - realignProgress, 3);
            const baseDx = d.currentDx * (1 - eased);
            const baseDy = d.currentDy * (1 - eased);

            // Phase 2 (>1s): circular drift fades in gradually over 2 seconds
            // so there's no sudden jump when the orbit begins
            const driftT = Math.max(0, t - 1);
            const driftEaseIn = Math.min(driftT / 2, 1); // 0→1 over 2 seconds
            const r = d.config.driftRadius * driftEaseIn;
            const s = d.config.driftSpeed;
            dx = baseDx + r * Math.sin(driftT * s);
            dy = baseDy + r * Math.cos(driftT * s * 1.3);
        } else {
            // Smooth interpolation toward mouse target (lerp)
            d.currentDx += (d.targetDx - d.currentDx) * 0.15;
            d.currentDy += (d.targetDy - d.currentDy) * 0.15;
            dx = d.currentDx;
            dy = d.currentDy;
        }

        d.offsets[0].setAttribute('dx', dx.toFixed(1));
        d.offsets[0].setAttribute('dy', dy.toFixed(1));
        d.offsets[1].setAttribute('dx', (-dx).toFixed(1));
        d.offsets[1].setAttribute('dy', (-dy).toFixed(1));

        _diplopiaAnimFrame = requestAnimationFrame(animate);
    };
    _diplopiaAnimFrame = requestAnimationFrame(animate);
}

function _stopDiplopiaTracking() {
    if (_diplopiaTracker) {
        const container = document.getElementById('vncContainer');
        if (container) container.removeEventListener('mousemove', _diplopiaTracker, true);
        _diplopiaTracker = null;
    }
    clearTimeout(_diplopiaIdleTimer);
    _diplopiaIdleTimer = null;
    if (_diplopiaAnimFrame) {
        cancelAnimationFrame(_diplopiaAnimFrame);
        _diplopiaAnimFrame = null;
    }
    _diplopia = null;
}


// =============================================
// 6. Mouse Tracking (for tunnel vision / scotoma)
// =============================================

function _startMouseTracking(container) {
    _stopMouseTracking();
    _visionMouseTracker = (e) => {
        if (_visionOverlays.length === 0) return;
        const rect = container.getBoundingClientRect();
        const x = ((e.clientX - rect.left) / rect.width * 100).toFixed(1) + '%';
        const y = ((e.clientY - rect.top) / rect.height * 100).toFixed(1) + '%';
        for (const el of _visionOverlays) {
            const mask = el._maskFn(x, y);
            el.style.webkitMaskImage = mask;
            el.style.maskImage = mask;
        }
    };
    // Use capture phase — noVNC's canvas may stopPropagation() on mousemove
    container.addEventListener('mousemove', _visionMouseTracker, true);
}

function _stopMouseTracking() {
    if (_visionMouseTracker) {
        const container = document.getElementById('vncContainer');
        if (container) container.removeEventListener('mousemove', _visionMouseTracker, true);
        _visionMouseTracker = null;
    }
}


// =============================================
// 7. Simulator HUD (floating pill + info overlay)
// =============================================

function _createSimulatorHUD() {
    const container = document.getElementById('vncContainer');
    if (!container) return;

    // HUD elements are appended to document.body (not #vncContainer) so they
    // are NOT affected by the CSS filter applied to the VNC container.
    // They use position: fixed and are repositioned to overlay the container.

    // --- Pill ---
    const hud = document.createElement('div');
    hud.id = 'simulatorHud';
    hud.className = 'simulator-hud';
    hud.innerHTML = `
        <svg class="simulator-hud-icon" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>
        </svg>
        <span class="simulator-hud-label"></span>
        <button class="simulator-hud-toggle on" title="Toggle simulation on/off"></button>
        <button class="simulator-hud-info-btn" title="About this condition">?</button>
    `;
    document.body.appendChild(hud);
    _hudElement = hud;

    // --- Info overlay ---
    const overlay = document.createElement('div');
    overlay.id = 'simulatorInfoOverlay';
    overlay.className = 'simulator-info-overlay';
    document.body.appendChild(overlay);
    _infoOverlayElement = overlay;

    // --- Event wiring ---
    hud.querySelector('.simulator-hud-toggle').addEventListener('click', _onHudToggleClick);
    hud.querySelector('.simulator-hud-info-btn').addEventListener('click', _onHudInfoClick);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) _closeInfoOverlay();
    });

    // --- Position tracking ---
    // Keep the HUD and info overlay anchored to the VNC container
    _positionHUD();
    const resizeObserver = new ResizeObserver(_positionHUD);
    resizeObserver.observe(container);
    window.addEventListener('resize', _positionHUD);
}

/** Position the HUD pill and info overlay to match the VNC container's bounds. */
function _positionHUD() {
    const container = document.getElementById('vncContainer');
    if (!container) return;
    const rect = container.getBoundingClientRect();

    if (_hudElement) {
        _hudElement.style.left = (rect.left + 16) + 'px';
        _hudElement.style.bottom = (window.innerHeight - rect.bottom + 16) + 'px';
    }

    if (_infoOverlayElement) {
        _infoOverlayElement.style.left = rect.left + 'px';
        _infoOverlayElement.style.top = rect.top + 'px';
        _infoOverlayElement.style.width = rect.width + 'px';
        _infoOverlayElement.style.height = rect.height + 'px';
    }
}

function _updateSimulatorHUD() {
    if (!_hudElement) return;

    if (_activeVisionProfile) {
        const profile = VISION_PROFILES[_activeVisionProfile];
        _hudElement.querySelector('.simulator-hud-label').textContent = profile.label;
        _hudElement.querySelector('.simulator-hud-toggle').classList.toggle('on', !_simulationPaused);
        _hudElement.classList.toggle('paused', _simulationPaused);
        // Show with animation (requestAnimationFrame ensures the transition triggers)
        requestAnimationFrame(() => _hudElement.classList.add('visible'));
    } else {
        _hudElement.classList.remove('visible');
    }
}

function _onHudToggleClick() {
    if (!_activeVisionProfile) return;

    _simulationPaused = !_simulationPaused;
    const container = document.getElementById('vncContainer');
    const profile = VISION_PROFILES[_activeVisionProfile];

    if (_simulationPaused) {
        // Remove visual effects but keep profile selected
        container.classList.remove('vision-filter-active');
        for (const el of _visionOverlays) el.style.display = 'none';
        if (_floaterContainer) _floaterContainer.style.display = 'none';
        _stopFilterAnimation();
        _stopDiplopiaTracking();
    } else {
        // Re-apply CSS filters from stored profile
        const filters = [];
        if (profile.svgFilter) filters.push(`url(#${profile.svgFilter})`);
        if (profile.cssFilter) filters.push(profile.cssFilter);
        if (filters.length) {
            container.style.setProperty('--vision-filter', filters.join(' '));
            container.classList.add('vision-filter-active');
        }
        // Unhide existing field overlays and floaters (don't recreate)
        for (const el of _visionOverlays) el.style.display = '';
        if (_floaterContainer) _floaterContainer.style.display = '';
        // Restart filter animation and diplopia tracking if profile has them
        if (profile.animateFilter) _startFilterAnimation(profile.animateFilter);
        if (profile.diplopiaTracking) _startDiplopiaTracking(container, profile.diplopiaTracking);
    }

    _updateSimulatorHUD();
}

function _onHudInfoClick() {
    if (!_activeVisionProfile) return;
    const info = VISION_INFO[_activeVisionProfile];
    const profile = VISION_PROFILES[_activeVisionProfile];
    if (!info || !_infoOverlayElement) return;

    _infoOverlayElement.innerHTML = `
        <div class="simulator-info-card">
            <button class="simulator-info-close" onclick="_closeInfoOverlay()">\u00d7</button>
            <div class="simulator-info-header">
                <h2>${_escHtml(info.medicalName)}</h2>
                <span class="simulator-info-badge">${_escHtml(info.category)}</span>
            </div>
            <div class="simulator-info-body">
                <div class="simulator-info-section">
                    <h3>What is it?</h3>
                    <p>${_escHtml(info.description)}</p>
                </div>
                <div class="simulator-info-section">
                    <h3>Prevalence</h3>
                    <p>${_escHtml(info.prevalence)}</p>
                </div>
                <div class="simulator-info-section">
                    <h3>Impact on web browsing</h3>
                    <p>${_escHtml(info.impact)}</p>
                </div>
            </div>
        </div>
    `;
    _infoOverlayElement.classList.add('show');
    document.addEventListener('keydown', _onInfoEscapeKey);
}

function _closeInfoOverlay() {
    if (_infoOverlayElement) _infoOverlayElement.classList.remove('show');
    document.removeEventListener('keydown', _onInfoEscapeKey);
}

function _onInfoEscapeKey(e) {
    if (e.key === 'Escape') {
        e.stopPropagation();
        _closeInfoOverlay();
    }
}

/** Simple HTML escaping for safe rendering of info text. */
function _escHtml(str) {
    const el = document.createElement('span');
    el.textContent = str;
    return el.innerHTML;
}


// =============================================
// 8. Toolbar Button State
// =============================================

function _updateVisionButtonState() {
    const btn = document.querySelector('[data-button-key="vision"] button');
    if (btn) {
        btn.classList.toggle('active', !!_activeVisionProfile);
    }
}


// =============================================
// 9. Vision Dropdown Rendering
// =============================================

function buildVisionDropdown() {
    const dropdown = document.createElement('div');
    dropdown.className = 'dropdown vision-dropdown';

    let menuHtml = '';
    let currentGroup = null;

    menuHtml += `<button class="dropdown-item vision-item${!_activeVisionProfile ? ' active' : ''}"
                         onclick="clearVisionSimulation(); closeVisionDropdown();">
        <svg viewBox="0 0 24 24"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>
        Normal Vision
    </button>`;

    for (const [id, profile] of Object.entries(VISION_PROFILES)) {
        if (profile.group !== currentGroup) {
            currentGroup = profile.group;
            menuHtml += `<div class="dropdown-divider"></div>`;
            menuHtml += `<div class="dropdown-section-label">${currentGroup}</div>`;
        }
        const isActive = _activeVisionProfile === id;
        menuHtml += `<button class="dropdown-item vision-item${isActive ? ' active' : ''}"
                             onclick="toggleVisionSimulation('${id}'); closeVisionDropdown();"
                             title="${profile.description}">
            ${isActive ? '<svg viewBox="0 0 24 24" class="vision-check"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>' : '<span class="vision-check-spacer"></span>'}
            ${profile.label}
        </button>`;
    }

    dropdown.innerHTML = `
        <button onclick="toggleVisionDropdownMenu(this)" title="Vision simulator">
            <svg viewBox="0 0 24 24"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>
            <span class="toolbar-btn-label">Vision</span>
            <svg viewBox="0 0 24 24" style="width:12px;height:12px;margin-left:2px;"><path d="M7 10l5 5 5-5z"/></svg>
        </button>
        <div class="dropdown-menu vision-menu">${menuHtml}</div>
    `;

    return dropdown;
}

function toggleVisionDropdownMenu(btn) {
    const menu = btn.nextElementSibling;
    const isOpen = menu.classList.contains('show');
    document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.remove('show'));
    if (!isOpen) {
        _rebuildVisionMenu(menu);
        menu.classList.add('show');
    }
}

function closeVisionDropdown() {
    document.querySelectorAll('.vision-menu').forEach(m => m.classList.remove('show'));
}

function _rebuildVisionMenu(menu) {
    let menuHtml = '';
    let currentGroup = null;

    menuHtml += `<button class="dropdown-item vision-item${!_activeVisionProfile ? ' active' : ''}"
                         onclick="clearVisionSimulation(); closeVisionDropdown();">
        <svg viewBox="0 0 24 24"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>
        Normal Vision
    </button>`;

    for (const [id, profile] of Object.entries(VISION_PROFILES)) {
        if (profile.group !== currentGroup) {
            currentGroup = profile.group;
            menuHtml += `<div class="dropdown-divider"></div>`;
            menuHtml += `<div class="dropdown-section-label">${currentGroup}</div>`;
        }
        const isActive = _activeVisionProfile === id;
        menuHtml += `<button class="dropdown-item vision-item${isActive ? ' active' : ''}"
                             onclick="toggleVisionSimulation('${id}'); closeVisionDropdown();"
                             title="${profile.description}">
            ${isActive ? '<svg viewBox="0 0 24 24" class="vision-check"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>' : '<span class="vision-check-spacer"></span>'}
            ${profile.label}
        </button>`;
    }

    menu.innerHTML = menuHtml;
}


// =============================================
// 10. Initialization
// =============================================

function initVisionSimulator() {
    // Inject SVG filter definitions into the page.
    // Must use DOMParser with 'image/svg+xml' to ensure SVG namespace is preserved.
    // Using div.innerHTML would parse as HTML, breaking SVG filter primitives
    // like feTurbulence and feDisplacementMap.
    const parser = new DOMParser();
    const svgDoc = parser.parseFromString(VISION_SVG_FILTERS, 'image/svg+xml');
    const svgEl = svgDoc.documentElement;
    document.body.appendChild(document.importNode(svgEl, true));
    // Create the HUD elements (hidden until a simulation is activated)
    _createSimulatorHUD();
}
