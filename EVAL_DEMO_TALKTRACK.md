# Reference Talktrack — Offline & Online Evaluation

**Repo:** `chat-langchain-lite` · **Timing:** ~30 min + Q&A
**Screen setup:** LangSmith left, chat UI right, GitHub in a third tab (pre-opened on the PR).

**The one-sentence story:** *Offline eval is how you decide what ships. Online eval is how you find out what you didn't test for. The two are joined by a golden dataset that only ever grows.*

---

## Pre-flight — do this the night before

| # | Step | Command / where |
|---|------|-----------------|
| 1 | Model creds in your **shell** (not `.env`) | see the routing box below |
| 2 | Sync deps | `uv sync` |
| 3 | Create project, datasets, online evaluators | `python -m scripts.setup` |
| 4 | Populate traces + threads | `python -m scripts.generate_traces` |
| 5 | GitHub → Settings → Secrets and variables → Actions | secrets: `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LANGSMITH_WORKSPACE_ID`; variable: `DEMO_PRESENTER` |
| 6 | GitHub → Actions tab → enable workflows | forks disable Actions by default |
| 7 | GitHub → Settings → Branches → protect `main` | require status check **“Offline evals (mandatory)”** |
| 8 | **Create an annotation queue** in LangSmith UI | `setup.py` does *not* create one |
| 9 | **Create an alert** on Feedback Score | `setup.py` does *not* create one |
| 10 | Have a failing PR ready but **not merged** | this is your Act 1 finale |

### Routing: gateway vs direct — one env var

`utils/models.py` uses a plain constructor and reads routing from the environment,
so the same code does both. Nothing to change in code:

```bash
# Through the LangSmith Gateway — UI pane shows "🛡 Routed via Gateway"
export ANTHROPIC_BASE_URL="https://gateway.smith.langchain.com/anthropic"
export ANTHROPIC_API_KEY="<your LangSmith API key>"   # ← NOT an Anthropic key

# Direct to Anthropic — UI pane shows "⚡ Direct connection"
export ANTHROPIC_BASE_URL="https://api.anthropic.com"
export ANTHROPIC_API_KEY="<your Anthropic key>"
```

> ⚠️ **The gotcha:** through the gateway, `ANTHROPIC_API_KEY` must hold your
> **LangSmith** key — the gateway authenticates with LangSmith credentials and
> injects the provider key itself. Setting the gateway URL but leaving an
> Anthropic key in place fails with a 401 that reads like a bad Anthropic key.
>
> Your machine's ambient `ANTHROPIC_BASE_URL` is currently
> `https://api.anthropic.com`, i.e. **direct**. Export the two vars above in the
> shell you demo from if you want the gateway beat.

> ⚠️ **Two things the setup script does not do:** annotation queues and alerts. Create both by hand or Act 2 has holes.
> ⚠️ **Sampling is hardcoded to 1.0** in `scripts/setup.py:246`. To tell the sampling story, drop one evaluator to `0.1` in the UI beforehand so you have both to compare.

---

## Act 1 — Offline Eval: deciding what ships

### 1.1 Golden Dataset Management (~3 min)

→ LangSmith → **Datasets** → `chat-lc-lite-scope-<you>`

*"This is the golden dataset. It's the contract for what 'working' means for this agent — every example is a case we've decided we must not regress on."*

*"Three things matter about how this is managed. First, provenance: these didn't come from someone's imagination, they came from real traces. Second, it's versioned — every edit creates a new version, and I can tag one. This one's tagged `baseline`."*

→ Click **Versions** tab → show the `baseline` tag

*"Third, and this is the part teams underestimate: this dataset is append-only in practice. It only grows, and it grows from production failures. That's the loop we'll close in the second half."*

> 🎙️ If asked "how big should it be?": start at 20–50 cases covering your known failure modes. Coverage of failure modes beats volume.

---

### 1.2 Scoring (~3 min)

→ **Evaluators** — open `evals/evaluators.py` in the editor alongside

*"Scoring is where teams either get rigor or get vibes. We support three kinds, and you want all three."*

- **Code evaluators** — deterministic. Did it call the tool? Is the JSON valid? Free and instant.
- **LLM-as-judge** — for the things you can't regex: tone, groundedness, did it actually answer.
- **Human** — the tiebreaker, via annotation queues. That's Act 2.

*"Ours returns a pass rate across assertions per example — so a score isn't a vibe, it's 'this example met 4 of 5 stated requirements.'"*

> 🎙️ **Expect the pushback:** *"Isn't an LLM grading an LLM circular?"*
> Answer: the judge is a different, cheaper model, doing a **narrower** task — a binary check against explicit criteria, not open-ended generation. And you validate the judge against human labels from the annotation queue. That's exactly what SME review is for.

---

### 1.3 Experiments & Comparison (~3 min)

→ **Experiments** tab on the dataset → open two runs → **Compare**

*"Every eval run is an experiment — a permanent, immutable record of one version of this agent against one version of the dataset."*

→ Show the comparison view, example-by-example

*"This is the view that actually changes behavior on a team. Not the average — the average hides everything. This is per-example: here's a case that regressed, here's the old output, here's the new one, side by side."*

*"Notice these are tagged with the model. Same dataset, same evaluators, different model — that's your model-migration decision made with evidence instead of a slide deck."*

> 🎙️ Land this line: *"Averages tell you something moved. Comparison tells you what broke."*

---

### 1.4 Release Gate (~4 min) — **the money moment**

→ GitHub tab → the open PR

*"Everything so far is useful but voluntary. Here's where it becomes policy."*

→ Show `.github/workflows/evals.yml`

*"Every PR to main runs the eval suite against the golden dataset. Not on demand — every PR. The threshold is 0.7."*

→ Scroll the PR to the checks section, show the ❌

*"This PR scored below threshold. And look —"*

→ Point at the greyed-out merge button

*"— merge is blocked. Not 'discouraged in a code review comment.' Blocked. A regression on the golden dataset is now the same class of event as a failing unit test."*

→ Click into the Actions run → show eval output → click through to the experiment in LangSmith

*"And the CI run isn't a black box. It produced a real experiment in LangSmith, so when the gate fails you're one click from the exact examples that failed and why."*

→ Now push the fix (or merge the passing PR) → check goes ✅ → merge

*"That's the release gate. The dataset defines the standard, CI enforces it, and no one has to remember to care."*

> 🎙️ **The escape hatch, if asked:** there's a `skip-evals` label. It's deliberate — you need a bypass for a docs typo. The control isn't that a bypass can't exist, it's that using it is *visible*: it's a label on the PR, in the audit trail, and who can apply it is itself a permission.

---

## Act 2 — Online Eval: finding what you didn't test for

*"Offline eval only tests what you thought to write down. Production will hand you inputs you never imagined. That's not a gap in your dataset — it's the permanent condition."*

### 2.1 Sampling & Scoring (~3 min)

→ Chat UI → ask a question → LangSmith → the live trace with scores attached

*"Same idea as offline — LLM-as-judge — but now running on live traffic with no reference output. So we're not asking 'did it match the expected answer,' we're asking reference-free questions: was it grounded, was it in scope, was it safe."*

→ **Evaluators** tab on the project → show sampling rate

*"Sampling is the cost lever. This one's at 100% because it's a demo. In production you'd run your cheap safety checks at 100% and your expensive judges at 10%."*

> ⚠️ **Know this one:** when an online evaluator runs on a trace, that trace auto-upgrades to extended data retention, which affects trace pricing. Sampling controls both judge cost *and* retention cost. Mentioning this unprompted reads as operator credibility.

---

### 2.2 Drift & Failure Detection (~3 min)

→ **Dashboards** → chart of a feedback key over time, grouped

*"Any single bad response is noise. What you care about is the trend."*

*"This is the average `scope_adherence` score over time. Nothing here is a crash — every one of these runs returned 200 and looked fine to the user. But the quality is sliding."*

*"That's the failure mode unique to agents: silent degradation. No exception, no error rate spike, just answers getting quietly worse. A prompt changed, a doc got stale, traffic shifted to a topic you're weak on."*

→ Group by model or tag to isolate it

> 🎙️ **Be precise here — don't overclaim.** LangSmith doesn't ship a button labelled "drift detection." Drift is *detected* by charting a feedback score over time and alerting on it. Say it that way; a technical audience will respect the precision and it's a better story anyway: the signal is your own eval score, not a vendor black box.

---

### 2.3 Alerting (~2 min)

→ **Alerts** → show the rule

*"Nobody watches a dashboard. So the dashboard watches itself."*

*"LangSmith alerts on five metrics: run count, cost, error count or rate, latency, and — the important one for us — **feedback score**. That last one means you can page someone on a *quality* regression, not just an outage."*

*"This rule says: if average `scope_adherence` drops below 0.8 over a one-hour window, alert. That fires into PagerDuty or a webhook."*

> 🎙️ The line that lands with platform teams: *"You already alert on 500s and p99 latency. This is alerting on whether the agent is still doing its job — and until now you had no metric for that."*

---

### 2.4 Annotation Queue & SME Review (~3 min)

→ **Annotation Queues** → open the queue

*"The alert told us something's wrong. Now a human decides what."*

*"Low-scoring traces route into an annotation queue. This is built for the subject-matter expert — the claims adjuster, the clinician, the support lead. Not the engineer."*

→ Walk one item: read the trace, apply a score, leave a note

*"They see the input, the output, and the judge's score. They give the ground-truth verdict. Two things come out of that. One, you find out whether your LLM judge is actually right — that's how you validate the judge instead of trusting it. Two, you get a corrected reference output."*

*"And that corrected output is the valuable artifact, because of what happens next."*

---

### 2.5 Closing the loop → Golden Dataset (~2 min)

→ From the annotation queue item → **Add to dataset** → pick the golden dataset

*"This production failure — the one nobody predicted, that the SME just corrected — is now a permanent example in the golden dataset."*

*"Which means from this moment on, every future PR is tested against it. This exact failure can never silently ship again. It's now enforced by the release gate we saw in Act 1."*

→ Draw the loop on screen with your cursor: **production → alert → queue → SME → dataset → release gate → production**

*"That's the whole system. Offline eval decides what ships. Online eval finds what you missed. The annotation queue turns a failure into a test case. And the release gate makes sure it stays fixed. Every incident makes the next release harder to break."*

> 🎙️ **This is your closing image.** Say it slowly. If they remember one thing, make it this loop.

---

## Act 3 — Enterprise Controls (~3 min)

*"One thing changes when you go from one agent to fifty: who gets to decide what 'passing' means."*

→ LangSmith → **Settings → Roles** (or the RBAC docs page)

*"The platform team owns the golden dataset and the mandatory evaluators. Agent teams consume them. Concretely, that's a custom role."*

| Capability | Permission | Platform | Builder |
|---|---|:--:|:--:|
| Run evals against the golden dataset | `datasets:read`, `datasets:download` | ✓ | ✓ |
| Modify / delete the golden dataset | `datasets:update`, `datasets:delete` | ✓ | ✗ |
| See the mandatory evaluators | `rules:read` | ✓ | ✓ |
| Edit or disable those evaluators | `rules:update`, `rules:delete` | ✓ | ✗ |
| Create experiments (needed to run evals) | `projects:create` | ✓ | ✓ |

*"An agent builder can run the suite and see exactly why they failed. They cannot lower the bar. That's the whole control in one sentence."*

→ GitHub → show `.github/CODEOWNERS`

*"Same boundary on the repo side. The workflow that defines the gate and the evaluator suite are CODEOWNER-protected — a team can't quietly drop the threshold from 0.7 to 0.2 in their own PR. It needs platform review."*

*"So you get a genuine paved road: central policy the platform team owns, self-service everywhere else."*

> 🎙️ **Honesty note:** custom roles are an Enterprise RBAC feature. If your workspace isn't Enterprise, present this as the target-state configuration — show the permission model and the CODEOWNERS file, don't fake a permission denial.

---

## Close (~2 min)

*"Three claims, and you saw all three:"*

1. *"**Offline eval** turns 'seems better' into a per-example, versioned, reproducible comparison — and a release gate that blocks the merge button."*
2. *"**Online eval** catches what your dataset never covered, alerts on quality rather than uptime, and routes it to the person qualified to judge it."*
3. *"**The loop closes.** Every production failure becomes a permanent test case. The system gets harder to break over time instead of easier."*

*"And none of that required a data science team. It required a dataset, a threshold, and a place to put the failures."*

---

## Quick reference

```bash
python -m scripts.setup             # project + datasets + online evaluators
python -m scripts.generate_traces   # 11 single-turn + 1 threaded conversation
python -m scripts.run_evals         # offline evals, prints scores
uv run langgraph dev                # chat UI + graph API → http://localhost:2024/
python -m scripts.cleanup           # reset between demos
```

| Thing | Value |
|---|---|
| Golden dataset | `chat-lc-lite-scope-<DEMO_PRESENTER>` |
| Tool dataset | `chat-lc-lite-tools-<DEMO_PRESENTER>` |
| Version tag | `baseline` |
| Gate threshold | `0.7` (`.github/workflows/evals.yml`) |
| Required check name | **Offline evals (mandatory)** |
| Bypass label | `skip-evals` |
| Online eval keys | `security_advice`, `scope_adherence`, `tool_usage`, `response_completeness`, `professional_tone`, `factual_accuracy` |

### If something breaks mid-demo

| Symptom | Do this |
|---|---|
| Agent errors on startup | Creds not in shell — `printenv ANTHROPIC_BASE_URL` |
| 401 from the model | Gateway URL set but `ANTHROPIC_API_KEY` still holds an *Anthropic* key; it must be the LangSmith key |
| UI pane says "Direct connection" | `ANTHROPIC_BASE_URL` isn't the gateway URL in *this* shell |
| CI check never appears | Actions not enabled on the fork (Actions tab) |
| Merge button enabled despite ❌ | Branch protection missing the required check |
| Eval run finds no dataset | `DEMO_PRESENTER` in GitHub Variables ≠ your local value |
| Online scores missing on a trace | Evaluator sampling < 1.0 — that trace wasn't sampled. Say so; it's the sampling story |
| Alert didn't fire | Alerts evaluate on a window; generate traffic *before* the section, not during |
