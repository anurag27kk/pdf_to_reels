# Video Reel — Product Requirements

## ICP Profiles

Three user profiles view videos in the same app. Profile is set at the user level — the app serves different video experiences based on who's logged in.

| Dimension | Doctor | Retailer / Stockist |
|-----------|--------|---------------------|
| Role | Prescribing physician | Pharmacy counter / distributor |
| Goal | Learn clinical details to prescribe confidently | Product training — know what they're selling |
| Default language | English | Hindi |
| Language switch | Can switch to Hindi | Can switch to English |
| Visual style | Professional, clinical | Friendly, product-training style |
| Content depth | Dense — MOA, PK, interactions, evidence | Simple — what it treats, customer FAQs, storage |
| Tone | Peer-to-peer, evidence-based | Conversational, practical, rep-explaining-to-you |

Retailer and stockist share the same video style and content. Treated as one profile going forward: **"field"** (vs "doctor").

---

## Language Requirements

### Default by profile
- **Doctor** → English audio + English on-screen text
- **Field (retailer/stockist)** → Hindi audio + Hindi on-screen text (Devanagari)

### Drug names
- Drug names are ALWAYS in English — spoken and on-screen — regardless of language
- Example Hindi narration: "AllerDuo mein **Bilastine 20mg** aur **Montelukast 10mg** hota hai, jo allergy aur asthma ke liye kaam karta hai"
- Example Hindi on-screen text: "AllerDuo — **Bilastine 20mg** + **Montelukast 10mg** | एलर्जी और अस्थमा के लिए"

### In-video language switching
- A toggle/button in the video player UI to switch language (e.g., "EN / HI" pill toggle)
- Switching language does NOT reload the video — it swaps the audio track and on-screen text overlay
- The visual frames (background images, icons, layout) stay the same
- This means each video needs:
  - 1 set of visual frames (shared)
  - 2 audio tracks (English + Hindi)
  - 2 sets of on-screen text overlays (English + Hindi)

### Implementation implication
- Gemini generates the same set of scene images for both languages
- Script generation (Claude) produces both English and Hindi narration per scene
- On-screen text has both English and Hindi versions in the script JSON
- Audio is generated separately per language
- Video player composites: frames + selected audio track + selected text overlay

---

## Visual Style — Doctor Profile

**Look:** Professional, clean, clinical. Think medical conference slide deck meets modern app.

**Reference:** Style 1 (navy-to-peach gradient) and Style 3 (blue professional) from concept frames.

| Element | Spec |
|---------|------|
| Background | Dark navy or deep blue gradients, clean and muted |
| Typography | Sans-serif (Inter/Outfit), white on dark. Bold headings, lighter body. |
| Icons/illustrations | Flat medical icons — lungs, molecules, pathways. Teal/white line art. |
| Color palette | Navy (#1a1a2e), white, teal (#00d2d3), subtle orange accents |
| Data presentation | Can show PK curves, comparison tables, receptor diagrams |
| Scene density | More text per frame is OK — doctors read fast |
| Branding | Product name + JagsonPal logo (subtle, corner placement) |
| Transitions | Clean fades and slides — no flashy animations |

**Vibe:** "I'm learning from a well-made pharma presentation on my phone."

---

## Visual Style — Field Profile (Retailer / Stockist)

**Look:** Friendly product training. Like a company rep is explaining the product using visual cards. Approachable, not intimidating.

**Reference:** Style 2 (dark card-based, Duolingo-ish) from concept frames — but warmer.

| Element | Spec |
|---------|------|
| Background | Warm dark charcoal or soft dark tones. Not as cold as doctor version. |
| Typography | Rounded sans-serif, larger text sizes. Hindi in Devanagari (Noto Sans Devanagari). |
| Icons/illustrations | Friendly, colored badge-style icons. Circular badges with bold colors. |
| Color palette | Charcoal base, orange (#e94560) badges, teal (#00d2d3) accents, warmer tones |
| Data presentation | NO tables, NO graphs. Only icon + short text cards. |
| Scene density | Less text per frame — one key point at a time |
| Branding | Product name prominent. JagsonPal branding more visible (builds trust with trade). |
| Transitions | Slightly more playful — slide-ups, card reveals |

**Vibe:** "My company is teaching me about this product in a fun, easy way."

### Key differences from doctor style

| Aspect | Doctor | Field |
|--------|--------|-------|
| Text per frame | 3-4 bullet points OK | 1-2 points max |
| Medical jargon | Use clinical terms (H1 antagonist, CysLT1) | Avoid — say "allergy blocker" instead |
| Drug mechanism | Show receptor pathways | Say "blocks what causes allergy symptoms" |
| Dosage info | Full clinical dosing, special populations | "1 tablet daily, as prescribed by doctor" |
| Interactions | Drug-drug interaction details | "Ask customer if they take blood thinners" |
| Visual metaphors | Molecular diagrams, pathway charts | Body part icons (nose = allergy, lungs = asthma) |

---

## Content Mapping Per Profile

Each product generates multiple reels. Same topics but different depth:

### Doctor reels (per product)
| Reel | Content | Duration |
|------|---------|----------|
| 1. Intro | Composition, formulation, drug class | 60s |
| 2. Indications | Clinical indications, patient selection | 60-90s |
| 3. Mechanism of Action | MOA per active ingredient, receptor-level detail | 90-120s |
| 4. Dosage & Safety | Dosing, contraindications, special populations | 90s |
| 5. Drug Interactions | Drug-drug, drug-food interactions, CYP metabolism | 60-90s |
| 6. Side Effects | ADRs, monitoring, patient counseling points | 60s |

### Field reels (per product)
| Reel | Content | Duration |
|------|---------|----------|
| 1. Product Overview | What is it, what's it for, who buys it | 60s |
| 2. Customer Questions | "What does this tablet do?" — simple answers | 60s |
| 3. Storage & Handling | Temperature, shelf life, packaging | 45-60s |
| 4. When to Recommend | Common symptoms/conditions that match | 60s |
| 5. Safety Basics | Common side effects to mention, when to refer to doctor | 60s |

Doctor gets 6 reels per product (deeper). Field gets 5 reels per product (simpler, practical).

---

## Video Structure (per reel)

```
[Scene 1: Title card — product name + topic]  (3-5s)
    |
[Scene 2-N: Content scenes — 1 key point each]  (10-20s each)
    |
[Final Scene: Summary + JagsonPal branding]  (3-5s)
    |
[Quiz starts — auto-transition, no menu]
```

### Per scene, we generate:
1. **Background image** — Gemini generates a styled frame matching the profile's visual style
2. **On-screen text** — overlaid on the image (English + Hindi versions)
3. **Audio narration** — TTS for that scene's narration (English + Hindi versions)

### Stitching
- Images displayed for scene duration (matched to audio length)
- Transitions between scenes (fade/slide)
- Audio plays over the image sequence
- On-screen text composited on top
- Language toggle swaps audio track + text layer in real-time

---

## Quiz Per Profile

After each reel, 4 quiz questions. Different question style per profile:

### Doctor quiz
| Type | Example |
|------|---------|
| MCQ (clinical) | "What receptor does Bilastine primarily block?" |
| Drug interaction | "A patient on Ketoconazole asks about AllerDuo. What's your concern?" |
| Scenario | "A pregnant patient with allergic rhinitis — is AllerDuo appropriate?" |

### Field quiz
| Type | Example |
|------|---------|
| MCQ (practical) | "AllerDuo is used for which condition?" |
| Customer scenario | "A customer asks if AllerDuo causes drowsiness. What do you say?" |
| True/False | "AllerDuo should be stored below 30 degrees C. True or False?" |

---

## Open Items

1. **Hindi TTS** — Which service for Hindi voiceover? Gemini TTS, Azure (best Hindi coverage), or ElevenLabs?
2. **On-screen text rendering** — Are we burning text into the image (Gemini generates it), or overlaying text programmatically during stitching? Overlay is better for language switching.
3. **Video format** — 9:16 vertical (Instagram reel style) confirmed? Or also need landscape for any use case?
4. **Intro/outro branding** — Does JagsonPal have brand assets (logo, colors, intro animation) or do we create them?
5. **Quiz language** — Should quiz questions also switch language with the toggle, or are they always in the profile's default language?
