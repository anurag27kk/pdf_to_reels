# Video Generation Evaluation — Detailed Scope

## Goal
Set up a prototype pipeline that takes a pharma PDF, generates a script, produces a voiceover, and renders an animated explainer video (60-120s). Evaluate quality across different tools and iterate on prompts until we get a good output.

---

## The Pipeline We're Building (Prototype)

```
PDF (e.g. AllerDuo.pdf)
    |
    v
[1. Extract Text] — pdftotext
    |
    v
[2. Generate Script] — Claude API
    |  "Take this drug info, write a 90-second narration script
    |   with scene breakdowns for an animated explainer"
    |
    v
[3. Generate Voiceover] — TTS API (Azure / ElevenLabs)
    |  Input: script text
    |  Output: MP3 audio file
    |
    v
[4. Render Video] — Video API (Creatomate / Remotion / Shotstack)
    |  Input: scene descriptions + voiceover audio + branding
    |  Output: MP4 video
    |
    v
[5. Review & Iterate]
    Watch the video, tweak prompts, re-render
```

---

## Tool Evaluation Matrix

We'll test **2 video renderers** and **2 TTS providers** across **1 drug product** (AllerDuo), producing the same reel with each combo to compare quality.

### Video Renderers to Evaluate

| Tool | Type | Why Test It | Setup Effort | Cost for Eval |
|------|------|-------------|-------------|---------------|
| **Creatomate** | Cloud API, template-based | Fastest to prototype. Visual editor + JSON API. Built-in TTS integration (ElevenLabs/Azure). Auto-subtitles. Auto-duration. | Low — sign up, design template, call API | ~$41/mo (Essential plan, 2000 credits) |
| **Remotion** | Self-hosted, React code | Most flexible. Full animation control. Free for small teams. Can use Claude Code to generate video code from prompts. Long-term cost advantage. | Medium-High — needs React + Lambda/local setup | Free (< 3 people) + AWS Lambda costs (pennies) |

**Why not Shotstack**: Requires manual timestamp calculation for every clip (high dev overhead), no keyframe animation, weaker animation than both alternatives. Not worth testing for this use case.

**Why not JSON2Video**: Smaller ecosystem, no Python SDK, less animation control than Creatomate. Skip for now.

### TTS Providers to Evaluate

| Provider | Why Test It | Hindi Quality | Drug Name Control | Cost for Eval |
|----------|-------------|--------------|-------------------|---------------|
| **Azure TTS** | Best bilingual Hindi+English. HD voices (Aarti/Arjun) built for code-switching. Best SSML/phoneme support for drug names. | 8.5/10 | Best — full SSML phoneme + custom lexicon XML. Works with ALL voice types. | **Free** (68K chars << 5M free tier) |
| **ElevenLabs** | Most natural-sounding voices. Good Indian English accents. | 7/10 | Limited — pronunciation dictionaries, but phoneme tags don't work with best models. | ~$22/mo (Creator plan, 100K chars) |

### Test Combinations

| Test | Video | TTS | Expected Style |
|------|-------|-----|---------------|
| A | Creatomate | Azure (Aarti HD, Hindi) | Template slides + bilingual narration |
| B | Creatomate | ElevenLabs (English) | Template slides + natural English narration |
| C | Remotion | Azure (Arjun HD, Hindi) | Custom animated scenes + bilingual narration |
| D | Remotion | ElevenLabs (English) | Custom animated scenes + natural English narration |

We evaluate all 4, pick the best combo, then iterate on that one.

---

## Detailed Steps

### Step 1: Extract Text from PDF
- Tool: `pdftotext` (already installed via poppler)
- Already done — we have the full text of all 3 products
- **No work needed**

### Step 2: Script Generation with Claude API
Build a prompt that takes extracted PDF text and outputs a structured script.

**Script output format** (JSON):
```json
{
  "title": "AllerDuo — What It Is and How It Works",
  "duration_target": "90 seconds",
  "language": "en",
  "scenes": [
    {
      "scene_number": 1,
      "duration": "15s",
      "narration": "AllerDuo combines two powerful ingredients...",
      "visual_description": "Product name and composition appearing on screen with molecular icons",
      "on_screen_text": ["Bilastine 20mg", "Montelukast 10mg"],
      "transition": "fade"
    },
    {
      "scene_number": 2,
      "duration": "20s",
      "narration": "It's indicated for allergic rhinitis and asthma...",
      "visual_description": "Icons showing nose/lungs with inflammation reducing",
      "on_screen_text": ["Allergic Rhinitis", "Asthma"],
      "transition": "slide_left"
    }
  ]
}
```

**Work items:**
- [ ] Write the Claude API prompt for script generation
- [ ] Test with AllerDuo PDF content
- [ ] Iterate on prompt until script quality is good (clear narration, logical scene flow, correct medical facts)
- [ ] Test Hindi script generation (same prompt, target language: Hindi)
- [ ] Build a simple Node.js/Python script that calls Claude API with PDF text

**Evaluation criteria for scripts:**
- Medical accuracy (does it match the PDF?)
- Natural narration flow (would it sound good read aloud?)
- Scene breakdown makes sense for animation
- Duration estimate is realistic (150 words/min speaking rate)

### Step 3: Voiceover Generation

#### Azure TTS Setup
- [ ] Create Azure account + Speech Services resource (free tier)
- [ ] Build a drug name pronunciation lexicon (XML):
  ```xml
  <lexicon>
    <lexeme><grapheme>Bilastine</grapheme><phoneme>bɪˈlæstiːn</phoneme></lexeme>
    <lexeme><grapheme>Montelukast</grapheme><phoneme>ˌmɒntəˈluːkæst</phoneme></lexeme>
    <lexeme><grapheme>Methylcobalamin</grapheme><phoneme>ˌmɛθɪlkoʊˈbæləmɪn</phoneme></lexeme>
    <!-- ... all drug names ... -->
  </lexicon>
  ```
- [ ] Test Hindi voice (Aarti HD) with bilingual script (Hindi explanation, English drug names)
- [ ] Test English voice (en-IN accent) with English script
- [ ] Output: MP3 files at 24kHz/128kbps

#### ElevenLabs Setup
- [ ] Sign up for Creator plan ($22/mo)
- [ ] Select voices: Indian English accent (e.g. "Riya K. Rao" or "Monika Sogam")
- [ ] Create pronunciation dictionary for drug names (alias rules)
- [ ] Test with same scripts
- [ ] Output: MP3 files

**Work items for both:**
- [ ] Write a script (Node.js or Python) that takes script JSON, generates audio per scene, and concatenates into one file
- [ ] Listen to both outputs, compare naturalness and drug name pronunciation

**Evaluation criteria for voiceover:**
- Drug name pronunciation accuracy
- Natural speaking rhythm
- Hindi-English switching smoothness (for bilingual)
- Audio quality (no artifacts, good volume)

### Step 4a: Creatomate Video Rendering

- [ ] Sign up for Essential plan ($41/mo)
- [ ] Design 1 base template in their visual editor:
  - 9:16 aspect ratio (vertical, mobile-friendly reel)
  - Brand colors / placeholder for logo
  - Scene layout: background color/image + title text + bullet points + bottom subtitle area
  - Transitions between scenes (fade/slide)
- [ ] Make template fields dynamic (title text, bullet points, background, audio)
- [ ] Write a script that:
  1. Takes the script JSON from Step 2
  2. Takes the audio MP3 from Step 3
  3. Maps scenes to Creatomate template modifications
  4. Calls Creatomate render API
  5. Downloads MP4 output
- [ ] Test with Azure voiceover and ElevenLabs voiceover

**Creatomate-specific considerations:**
- Built-in TTS integration exists — we could skip separate TTS step and let Creatomate call ElevenLabs/Azure directly in the RenderScript. Worth testing both approaches.
- Auto-subtitles feature — test if subtitles sync well with the voiceover.
- Node.js SDK available (`creatomate` npm package)

### Step 4b: Remotion Video Rendering

- [ ] Set up Remotion project (`npx create-video@latest`)
- [ ] Use Remotion AI Skills (`npx skills add remotion-dev/skills`) for Claude Code integration
- [ ] Build React components for:
  - `<IntroScene>` — product name, composition, brand splash
  - `<ContentScene>` — animated text + bullet points with `interpolate()` fade-in
  - `<MOAScene>` — mechanism of action with visual metaphors
  - `<OutroScene>` — summary, CTA
- [ ] Use `<Series>` to chain scenes sequentially
- [ ] Add `<Audio>` component for voiceover sync
- [ ] Use `<TransitionSeries>` for scene transitions (fade, slide)
- [ ] Build a render script that takes scene JSON and renders MP4
- [ ] Test locally first, then optionally deploy to Lambda

**Remotion-specific considerations:**
- Full animation control — can do more interesting motion graphics
- Higher dev effort but reusable components
- Claude Code can generate Remotion code from prompts — leverage this for fast iteration
- Free for teams of 3 or fewer
- Rendering: local first (1-3 min per video), Lambda later (10-30s per video)

### Step 5: Compare & Iterate

Create a simple evaluation rubric:

| Criteria | Weight | Test A | Test B | Test C | Test D |
|----------|--------|--------|--------|--------|--------|
| Visual quality | 25% | | | | |
| Narration quality | 25% | | | | |
| Drug name pronunciation | 15% | | | | |
| Scene flow / pacing | 15% | | | | |
| Engagement (would a rep watch this?) | 10% | | | | |
| Ease of iteration | 10% | | | | |

After scoring, pick the winning combo and do 2-3 more iteration rounds on:
1. Script prompt refinement
2. Template/animation design
3. Voice selection and pronunciation tuning

---

## Work Breakdown

| Task | Description | Effort | Dependencies |
|------|-------------|--------|-------------|
| **2.1** Script prompt engineering | Write + iterate Claude API prompt for script generation | 2-3 hours | PDF text (done) |
| **2.2** Script generation script | Node.js/Python script to call Claude API | 1-2 hours | Claude API key |
| **3.1** Azure TTS setup | Create account, build drug name lexicon, test voices | 2-3 hours | Azure account |
| **3.2** ElevenLabs setup | Create account, select voices, build pronunciation dict | 1-2 hours | ElevenLabs account |
| **3.3** TTS generation script | Script to generate audio from text, per-scene or full | 2-3 hours | 3.1 or 3.2 |
| **4.1** Creatomate setup | Sign up, design template in editor | 2-3 hours | Creatomate account |
| **4.2** Creatomate render script | Script to call render API with scene data + audio | 2-3 hours | 4.1 + 3.3 |
| **4.3** Remotion project setup | Init project, install skills, build basic scene components | 3-4 hours | Node.js + React |
| **4.4** Remotion scene components | Build intro/content/MOA/outro components with animations | 4-6 hours | 4.3 |
| **4.5** Remotion render integration | Script to render video from scene JSON + audio | 2-3 hours | 4.4 |
| **5.1** Generate test videos | Run all 4 test combinations | 2-3 hours | All above |
| **5.2** Evaluate + iterate | Watch, score, refine prompts, re-render | 3-4 hours | 5.1 |

### Suggested Order of Execution

**Phase A — Script + TTS (do first, needed by both video options)**
1. Task 2.1 + 2.2 — Script generation (Claude API)
2. Task 3.1 + 3.2 — Set up both TTS providers
3. Task 3.3 — Build TTS generation script
4. Listen to voiceovers, quick sanity check

**Phase B — Video Rendering (can be parallel if 2 people)**
5. Task 4.1 + 4.2 — Creatomate path
6. Task 4.3 + 4.4 + 4.5 — Remotion path

**Phase C — Evaluation**
7. Task 5.1 — Generate all 4 test videos
8. Task 5.2 — Evaluate and iterate on the winner

---

## Accounts / API Keys Needed

| Service | Plan | Cost | What You Need |
|---------|------|------|--------------|
| Claude API (Anthropic) | Pay-per-use | ~$0.01-0.10 per script | API key |
| Azure Speech Services | Free tier | $0 | Azure account + resource key |
| ElevenLabs | Creator | $22/mo | API key |
| Creatomate | Essential | $41/mo | API key |
| AWS (for Remotion Lambda) | Pay-per-use | ~$0.01 per render | AWS account (optional, can render locally) |

**Total evaluation cost: ~$63/month** (ElevenLabs + Creatomate). Azure and Claude API are negligible. Remotion is free.

---

## What We'll Have at the End

1. A working prototype script that: PDF -> Script -> Voiceover -> Video
2. A clear winner between Creatomate vs Remotion for our use case
3. A clear winner between Azure TTS vs ElevenLabs for Hindi+English pharma narration
4. Refined Claude API prompts that produce good educational scripts
5. A drug name pronunciation lexicon for TTS
6. 4+ sample videos to show JagsonPal for feedback
7. A decision on the production architecture for the full service

---

## Open Decision After Evaluation

Based on evaluation results, we'll decide:

- **If Creatomate wins**: Lower dev effort, faster to production. Pay per video. Good for < 500 videos/month.
- **If Remotion wins**: Higher dev effort upfront, but free rendering, unlimited customization, better animations. Good for scale (500+ videos/month) or if we need precise visual control.
- **Hybrid option**: Use Remotion for the animation engine + Creatomate for assembly/subtitles. Or use Remotion for everything.
