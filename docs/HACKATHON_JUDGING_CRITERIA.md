# Hackathon Judging Criteria Reference

## Purpose

This document defines the judging criteria for the hackathon. Use it to evaluate all technical decisions, feature prioritization, and presentation planning against what judges will score.

---

## Scoring Dimensions (4 categories, assume equal weight)

### 1. Innovation and Creativity

**What judges look for:**

- Original thinking that challenges assumptions or reframes the problem
- Creative risk-taking — combining ideas in unexpected ways
- Must still deliver practical, real-world value (novelty alone won't score)

**Implementation signals:**

- Novel application of AI to an existing operational problem
- Unexpected data combinations or workflow integrations
- Reframing a known pain point from a new angle
- Avoiding "yet another chatbot" or generic dashboard patterns

**Anti-patterns:**

- Wrapping an LLM API call in a UI with no domain logic
- Rebuilding something that already exists without meaningful differentiation
- Innovation theater — impressive tech with no practical grounding

---

### 2. Technical Execution

**What judges look for:**

- Solution functions reliably — no demo crashes, no "imagine this works"
- Well-executed design, implementation, and usability
- Evidence of care in engineering decisions

**Implementation signals:**

- Working demo with real or realistic data
- Clean error handling — graceful failures, not stack traces
- Responsive, intuitive UI that doesn't require explanation
- Appropriate technology choices (not over-engineered, not under-built)
- Code quality: typed, structured, tested where critical

**Anti-patterns:**

- Hardcoded demo paths that break on any deviation
- Over-engineering (k8s cluster for a weekend project)
- Ignoring edge cases visible during a live demo
- Raw API responses displayed without processing

**Demo hardening checklist:**

- [ ] Works offline or handles network failures gracefully
- [ ] Handles empty states (no data, first run)
- [ ] Loading states for async operations
- [ ] At least one non-happy-path scenario tested
- [ ] Demo data is realistic, not lorem ipsum

---

### 3. Business Viability

**What judges look for:**

- Practical and usable by real teams or venues
- Clear adoption path — not theoretical
- Solves a real problem with measurable impact

**Implementation signals:**

- Specific target user persona (shift manager, event coordinator, F&B director)
- Week 1 adoption story: "Install → configure → value in under an hour"
- Cost model awareness (API costs, infrastructure, maintenance)
- Integration with tools teams already use (POS systems, scheduling tools, HubSpot, Slack)
- Data privacy and governance considerations addressed

**Anti-patterns:**

- "This could be used by anyone" — no specific user
- Requiring months of custom integration before value
- Ignoring operational realities (training, change management, shift handoffs)
- No mention of cost or sustainability

---

### 4. Presentation Quality

**What judges look for:**

- Clear narrative arc: problem → insight → solution → impact
- Smooth, understandable demo
- Strong explanation of impact and what's next

**Presentation structure:**

1. **Problem** (30s): Specific, quantified pain point. "X costs Y per Z."
2. **Insight** (30s): Why existing approaches fail. What's the unlock?
3. **Solution** (60s): What we built. Architecture at a glance.
4. **Demo** (2-3min): Live walkthrough of the core workflow. No slides during demo.
5. **Impact** (30s): Measured or projected results. Before/after.
6. **Adoption** (30s): How a team starts using this Monday morning.
7. **What's next** (15s): Roadmap hint — shows you've thought beyond the hackathon.

**Anti-patterns:**

- Starting with "We used React and Python and OpenAI and..."
- Slides-only with no working demo
- Demo without narration or context
- Apologizing for bugs or incomplete features during presentation

---

## Judge-Specific Considerations

### Matt Cooke — GM, F&B, Save on Foods Memorial Centre

- **Domain**: Venue food & beverage operations at scale
- **Values**: Measurement-driven decisions, sustainability/waste reduction, shift-level execution reliability, guest experience
- **Background**: Environmental engineering — responds to data and systems thinking
- **Impress him with**: Real operational metrics, waste reduction quantification, solutions that work "shift after shift"
- **Avoid**: Abstract AI promises without operational grounding

### Lautaro Cepeda — CRO, Personize.ai

- **Domain**: GenAI applied to full customer journey
- **Values**: End-to-end AI workflows (not point solutions), customer context, responsible AI adoption, real pilot evidence
- **Background**: HubSpot ecosystem, marketing/sales/engagement AI
- **Impress him with**: Connected workflows across touchpoints, context-aware AI reasoning, adoption metrics from real testing
- **Avoid**: Isolated automations, "we could integrate with..." without showing it

### Steve Harris — Founder, AI4 Enterprise

- **Domain**: Enterprise GenAI consulting, architecture, governance
- **Values**: RAG, multi-agent systems, small/tiny LLMs, practical adoption, security, governance
- **Background**: 40+ years tech leadership, certified across AWS/Azure/GCP/IBM AI platforms, local Victoria AI community leader
- **Impress him with**: Clean architecture diagrams, governance/data privacy awareness, efficient model selection (not defaulting to GPT-4 for everything), RAG implementations
- **Avoid**: Hand-waving on architecture, ignoring security/data handling, using large models where small ones suffice

---

## Decision Framework

When making any technical or design decision, score it against:

| Question | Maps to |
|---|---|
| Is this a novel approach or just standard CRUD + LLM? | Innovation |
| Does this work reliably in a live demo? | Technical Execution |
| Would a real venue/team pay for and adopt this? | Business Viability |
| Can we explain this clearly in under 5 minutes? | Presentation |

**If a feature scores low on 3+ dimensions, cut it. If it scores high on all 4, prioritize it.**

---

## Priority Stack for Build Decisions

1. **Core demo flow works end-to-end** (Technical Execution + Presentation)
2. **One innovative feature that differentiates** (Innovation)
3. **Real/realistic data and metrics** (Business Viability + Innovation)
4. **Polish: loading states, error handling, UI cleanup** (Technical Execution)
5. **Stretch features only if core is rock solid** (Innovation, but risky)

Never sacrifice demo reliability for feature count.
