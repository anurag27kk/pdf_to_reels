# JagsonPal Pharma — Video Reel + Trivia Service Scope

## Objective
Convert JagsonPal Pharma's PDF product content into daily 60-120 second educational video reels for pharma sales reps, with a post-video trivia/Q&A, engagement tracking, and spaced repetition — delivered through the existing Swish mobile app.

---

## 1. Content Analysis

### Source Material
3 drug products (5 PDFs, 2 are AllerDuo duplicates):

| Product | Composition | Therapeutic Area | Content Size |
|---------|------------|-----------------|-------------|
| **AllerDuo** | Bilastine 20mg + Montelukast 10mg | Allergic rhinitis, Asthma | ~285 lines — full monograph (MOA, PK, drug interactions, contraindications) |
| **Tibrolin** | Trypsin 48mg + Bromelain 90mg + Rutoside 100mg | Anti-inflammatory, joint health, post-surgery | ~140 lines — patient leaflet style |
| **Subneuro-NT** | Methylcobalamin 1500mcg + Pregabalin 75mg + Nortriptyline 10mg | Neuropathy, nerve pain, anxiety | ~92 lines — clinical pharmacology focused |

### Content-to-Reel Mapping
Each product can be broken into 4-6 daily reels:

| Reel # | Topic | Duration | Content Source |
|--------|-------|----------|---------------|
| 1 | Product intro — what it is, composition | 60s | Sections 1-3 |
| 2 | Indications — when to prescribe | 60-90s | Section 4.1 |
| 3 | Mechanism of action — how it works | 90-120s | Section 5.1 |
| 4 | Dosage, contraindications, warnings | 90s | Sections 4.2-4.4 |
| 5 | Drug interactions + special populations | 60-90s | Sections 4.5-4.6 |
| 6 | Side effects + patient counseling | 60s | Sections 4.8, 9 |

**Estimated total**: ~15-18 reels across all 3 products for the initial batch.

---

## 2. Current Platform State

The Swish platform currently has **zero video infrastructure**:
- No video upload type in upload-service
- No video streaming or playback
- No video player component
- Upload-service handles images, audio, documents only
- Mobile app is React Native, backend is Go microservices + GraphQL BFF

**Everything below needs to be built from scratch.**

---

## 3. Video Generation — Recommended Approach

### Option A: Avatar-Based (Talking Head) — RECOMMENDED FOR MVP
A realistic AI presenter explains drug info on screen. Professional, trust-building, easy to produce.

| Stage | Tool | Cost |
|-------|------|------|
| Script generation | Claude API — generate educational scripts from PDF content | ~$0.01-0.05/script |
| Voiceover | ElevenLabs (best quality) or Azure TTS (best Indian language coverage — 13 languages) | ~$0.01-0.05/min |
| Avatar video | **HeyGen API** (Scale tier) — best lip-sync, 175+ languages, Hindi/Tamil/Telugu support | ~$0.50/min |
| Assembly | Shotstack API — add branded intro/outro, subtitles, logo overlay | ~$0.20/video |
| **Total per 1-min video** | | **~$0.75-1.50** |

**Why HeyGen**: Best lip-sync quality, dedicated API pricing ($330/mo Scale tier at $0.50/credit), 175+ languages including Indian regional, 1080p output.

### Option B: Template-Based (Animated Infographic) — CHEAPEST
No avatar. Animated slides with text, charts, drug info cards + voiceover narration. Think animated PowerPoint.

| Stage | Tool | Cost |
|-------|------|------|
| Script generation | Claude API | ~$0.01-0.05/script |
| Voiceover | ElevenLabs or Azure TTS | ~$0.01-0.05/min |
| Video rendering | **Creatomate** (template-based, JSON API) or **Remotion** (React, self-hosted, free) | ~$0.10-0.30/video (Creatomate) or $0 (Remotion) |
| **Total per 1-min video** | | **~$0.15-0.35** |

**Why this is cheaper**: No avatar costs. But looks less personal/engaging.

### Option C: Hybrid — PREMIUM
Avatar presenter for intro/key points + Sora 2 for MOA animations (molecule visualizations, body system diagrams) + Shotstack to stitch. Most expensive (~$2-5/video) but highest production value.

### Recommendation
**Start with Option A (HeyGen)** for the first batch of 15-18 reels. If the client wants to scale to hundreds of products, switch to Option B (Creatomate/Remotion) for cost efficiency.

### TTS for Indian Languages
| Provider | Indian Languages | Quality | Price |
|----------|-----------------|---------|-------|
| **Azure TTS** | 13 (Hindi, Tamil, Telugu, Kannada, Bengali, Malayalam, Marathi, Gujarati, etc.) | Very good | $16/M chars |
| **ElevenLabs** | Hindi, Tamil (best quality for these two) | Best-in-class | ~$82.50/mo Pro |
| Google Cloud TTS | Hindi, Bengali, Tamil, Telugu, Kannada, Malayalam | Good | $16/M chars |
| Amazon Polly | Hindi only | OK | $16/M chars — skip |

**Recommendation**: Azure TTS for breadth, ElevenLabs for quality on Hindi/English.

---

## 4. Video Pipeline Architecture

```
PDF Upload
    |
    v
[Content Extraction] — pdftotext / existing mind-service OCR
    |
    v
[Script Generation] — Claude API
    |  Input: extracted text + reel template (intro/MOA/dosage/etc.)
    |  Output: 60-120s narration script + on-screen text points
    |
    v
[Quiz Generation] — Claude API (in parallel)
    |  Input: same extracted text + script
    |  Output: 3-5 MCQ/T-F questions with answers + explanations
    |
    v
[Human/MLR Review] — Admin dashboard
    |  Pharma client reviews script + questions for medical accuracy
    |  MANDATORY for pharma — cannot skip this step
    |
    v
[Video Generation] — HeyGen API (avatar) or Creatomate (template)
    |  Input: approved script
    |  Output: MP4 video file
    |
    v
[Post-Processing] — Shotstack or FFmpeg
    |  Add: branded intro/outro, subtitles, logo watermark
    |
    v
[Upload to S3 + CDN] — CloudFront for streaming
    |
    v
[Publish to App] — available in mobile app feed
```

### New Service Required: `reel-service`
A new Go microservice to manage the entire pipeline:

**Core entities:**
- `Reel` — metadata (product, topic, duration, status, video_url, thumbnail_url)
- `ReelScript` — generated script text, review status
- `ReelQuestion` — quiz questions per reel, with answers/explanations
- `ReelView` — per-user view events (opened, watch_time, completed, drop_off_point)
- `ReelQuizAttempt` — per-user quiz responses (question_id, answer, correct, time_taken_ms)
- `UserReelProgress` — spaced repetition state (easiness_factor, interval, next_review_date)

**API endpoints:**
- `POST /reels/generate` — trigger pipeline from PDF
- `GET /reels` — list available reels (paginated, filtered by product/status)
- `GET /reels/:id` — get reel details + video URL + questions
- `POST /reels/:id/view` — track view event
- `POST /reels/:id/quiz/submit` — submit quiz answers
- `GET /users/:id/review-queue` — get today's spaced repetition questions
- `GET /users/:id/stats` — engagement stats, streaks, scores
- Admin endpoints for MLR review workflow

---

## 5. Post-Video Trivia/Q&A

### UX Flow
```
[Video plays (60-120s)]
    |
    | video ends, auto-transition (no menu screen)
    v
[Question 1 of 4] — MCQ with 4 options
    |
    | tap answer -> instant feedback
    | correct: green flash + "Correct!" + move to next
    | wrong: red flash + correct answer shown + 1-line explanation
    v
[Question 2 of 4] — True/False
    v
[Question 3 of 4] — MCQ
    v
[Question 4 of 4] — Scenario-based ("A doctor asks about X, you say...")
    v
[Score Screen]
    | "You scored 3/4!"
    | XP earned, streak count, badge progress
    | "Review missed questions tomorrow"
    | [Next Reel] [Back to Feed]
```

### Question Types (recommended mix per reel)
| Type | Count | Example |
|------|-------|---------|
| MCQ (4 choices) | 2 | "What is the primary indication for AllerDuo?" |
| True/False | 1 | "AllerDuo can be taken with grapefruit juice. T/F" |
| Scenario-based MCQ | 1 | "A patient on aspirin asks about AllerDuo. What do you advise?" |

### Auto-Generation Pipeline
1. **Input**: PDF text + video script for that reel
2. **Generator**: Claude API with structured prompt — "Generate 4 questions from this content, 2 MCQ + 1 T/F + 1 scenario. Output JSON with question, options, correct_answer, explanation, source_quote."
3. **Validation**: Automated check that every answer traces back to a specific quote in the source PDF
4. **MLR Review**: Human pharma reviewer approves/edits before publish
5. **Storage**: Questions stored in reel-service DB, served via API

### Ensuring Pharma Accuracy
- LLM is constrained to ONLY the provided PDF content (no general knowledge)
- Every generated answer must include a `source_quote` field pointing to the exact sentence in the PDF
- MLR (Medical-Legal-Regulatory) review is mandatory before any content goes live
- Consider integrating with Veeva PromoMats for audit trail if client requires it

---

## 6. Engagement & Analytics

### Metrics to Track

**Video metrics:**
| Metric | How |
|--------|-----|
| Open rate | Track when reel is tapped |
| Watch time (seconds) | Video player progress events |
| Completion rate | Did they watch to the end? |
| Drop-off point | Timestamp where they stopped |
| Replay rate | Watched same reel again |

**Quiz metrics:**
| Metric | How |
|--------|-----|
| Quiz start rate | % who began quiz after video |
| Quiz completion rate | % who finished all questions |
| Score per reel | Correct / total |
| Time per question | Milliseconds from display to answer |
| Retry rate | % who retook after failing |

**Engagement metrics:**
| Metric | How |
|--------|-----|
| Daily active learners | Unique users who watched 1+ reel/day |
| Streak length | Consecutive days of reel completion |
| Knowledge mastery | % of questions in "mastered" state (SM-2 interval > 30 days) |
| Product coverage | % of reels completed per product |

### Gamification Layer
| Feature | How It Works |
|---------|-------------|
| **Streaks** | Consecutive days watching 1+ reel. Lost if a day is missed. (Duolingo-style loss aversion) |
| **XP Points** | +10 XP per reel watched, +5 XP per correct answer, +20 bonus for perfect score |
| **Leaderboard** | Weekly team/individual rankings by XP. Research shows leaderboard participation correlates with completion (p<0.01) |
| **Badges** | "AllerDuo Expert" after mastering all AllerDuo reels. Per-product badges. |
| **Levels** | Trainee -> Specialist -> Expert per therapeutic area |

---

## 7. Spaced Repetition (SM-2 Algorithm)

When a rep gets a question wrong, it re-enters a review queue using the SM-2 algorithm:

**How it works:**
- Each question per user has: `easiness_factor` (starts 2.5), `interval` (days until next review), `repetition_count`
- **Got it right easily** -> interval grows: 1 day -> 6 days -> 15 days -> 40 days...
- **Got it right with effort** -> interval grows slower
- **Got it wrong** -> interval resets to 1 day, question re-enters daily review pool

**User experience:**
- App shows a "Review" section: "You have 5 questions to review today"
- These are pulled from the SM-2 scheduler
- Over time, mastered questions fade away; weak areas keep coming back
- This is exactly how Duolingo and Anki work

---

## 8. Infrastructure Changes Required

### New service: `reel-service` (Go)
- Video pipeline orchestration
- Quiz management
- Engagement tracking
- Spaced repetition engine
- Admin/MLR review endpoints

### Changes to existing services:
| Service | Change |
|---------|--------|
| **upload-service** | Add `video` upload type + S3 bucket for video storage |
| **swish-bff** | New GraphQL queries/mutations for reels, quiz, stats |
| **node-page-orchestrator** | New page component type for reel feed |
| **Mobile app (React Native)** | Video player, quiz UI, review queue, gamification UI |

### New infrastructure:
| Component | Purpose | Cost Estimate |
|-----------|---------|---------------|
| AWS CloudFront | CDN for video streaming | ~$0.085/GB transfer |
| AWS MediaConvert (optional) | Transcode videos to HLS for adaptive streaming | ~$0.024/min |
| S3 bucket for videos | Storage | ~$0.023/GB/month |
| HeyGen API subscription | Video generation | $330/mo (Scale) |
| ElevenLabs or Azure TTS | Voiceover | $82.50/mo or $16/M chars |
| Claude API | Script + quiz generation | Pay per use, ~$0.01-0.10/reel |

---

## 9. Estimated Work Breakdown

| Component | What | Effort |
|-----------|------|--------|
| **reel-service** | New Go microservice — pipeline, quiz, analytics, spaced repetition | Large |
| **Admin dashboard** | MLR review UI for scripts + questions | Medium |
| **upload-service changes** | Add video type, S3 config | Small |
| **BFF changes** | GraphQL schema for reels | Medium |
| **Mobile — video player** | React Native video component + streaming | Medium |
| **Mobile — quiz UI** | Post-video quiz flow, feedback, score screen | Medium |
| **Mobile — gamification** | Streaks, XP, leaderboard, badges, review queue | Medium-Large |
| **Mobile — reel feed** | Feed/discovery UI for browsing reels | Medium |
| **Video pipeline integration** | HeyGen/Creatomate API integration, Shotstack assembly | Medium |
| **Content generation pipeline** | Claude API prompts for scripts + questions | Small-Medium |
| **Analytics dashboard** | Engagement metrics visualization for admin/client | Medium |

---

## 10. Open Questions for You

### Product/Business Questions
1. **Video style preference**: Does JagsonPal want a talking-head avatar presenter, or animated infographic slides, or both? This changes cost 5-10x.
2. **Languages**: Which Indian languages are needed? Just English + Hindi? Or Tamil, Telugu, Kannada, etc.? This affects TTS choice.
3. **How many products total?** Just these 3 for now, or is there a roadmap for 50+ products? This affects build-vs-buy and cost optimization.
4. **MLR review**: Does JagsonPal have an existing MLR review process? Do they use Veeva or similar? Or do we need to build a review workflow from scratch?
5. **Branding**: Do they have brand guidelines, intro/outro templates, logo assets for the videos?
6. **Publishing cadence**: Literally one new reel per day? Or batch-publish and drip-feed?

### Technical Questions
7. **The play button you mentioned** — is this already built in the mobile app, or is it planned? The codebase exploration found zero video infrastructure.
8. **Who generates the content?** Do we auto-generate scripts from PDFs (faster, cheaper) or does JagsonPal provide scripts and we just produce the video?
9. **Offline support**: Do reps need to watch reels offline (common in rural India with spotty connectivity)? This changes the streaming vs download architecture.
10. **Existing analytics stack**: Is there Mixpanel/Amplitude/custom analytics already in the app? Or do we build from scratch?
11. **Push notifications**: Should reps get daily reminders ("Your daily reel is ready!")? This needs notification infrastructure.
12. **Admin access**: Does JagsonPal get their own admin dashboard to see engagement stats, or just periodic reports?

---

## 11. Phased Delivery Suggestion

### Phase 1 — MVP (Video + Basic Quiz)
- Video generation pipeline (HeyGen + Claude API)
- Upload + stream videos in the mobile app
- Basic post-video quiz (4 questions, MCQ only)
- Simple score screen
- Basic analytics (open rate, completion, score)

### Phase 2 — Engagement
- Gamification (streaks, XP, leaderboard)
- Spaced repetition review queue
- Richer question types (scenario-based, T/F)
- Admin dashboard for MLR review
- Push notifications for daily reels

### Phase 3 — Scale
- Multi-language support (regional Indian languages)
- Template-based video generation (Creatomate/Remotion) for cost efficiency at scale
- Advanced analytics dashboard for JagsonPal
- Offline video download support
- Badges and levels per therapeutic area
