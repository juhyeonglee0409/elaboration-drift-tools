# elaboration-drift-tools

Analytical tools and supplementary materials for two companion papers:

- **Lee, J. (2026a).** *Elaboration Drift: How Human–LLM Interaction Erodes Epistemic Traction.* Preprint.
- **Lee, J. (2026b).** *Beyond Sycophancy: Measuring Hallucination-Free Convergence in Long-Term Human–LLM Interaction.* Preprint.

## Overview

These papers identify and measure a convergence phenomenon in long-term human–LLM interaction that persists after sycophancy has been suppressed and hallucination removed. The philosophical paper (2026a) analyzes why this residual is structurally invisible to epistemic vigilance and metacognitive monitoring. The measurement paper (2026b) documents its magnitude across 12,925 relays and 391 sessions with GPT-4, GPT-4o, GPT-5, Claude, and Gemini.

This repository provides the tools and materials needed for independent replication and reanalysis.

## Contents

### `bs-analyzer/`

The auto-classification tool (BS Analyzer v2.2) used in Lee (2026b). Two equivalent implementations reading from a shared configuration file:

- `bs_analyzer.html` — Standalone browser application. No dependencies.
- `bs_analyzer.py` — Python 3 script. No external packages required.
- `bs_keywords_v22.json` — Shared keyword dictionary and classification parameters. User-modifiable for adaptation to other languages and datasets.

The tool implements a two-stage classification logic (convergence detection → directional classification) producing four verdict categories: *drowning*, *headway*, *doldrums*, and *unclassified*. Full details in Lee (2026b), Section 2.3.

### `validation/`

Materials for the blind validation protocol described in Lee (2026b), Section 2.8:

- `blind_validation_set.json` — 58 relay items (30 tool-flagged + 28 non-flagged after data quality exclusions), randomized, flag status concealed.
- `coding_manual.md` — Operationalized definitions for three morphological forms (elevation, idealization, doubt absorption) with examples and an ambiguity rule.

### `supplementary/`

- `user_b_conversation_anonymized.md` — Anonymized messenger conversation between the researcher and User B (Supplementary Material S2). Pseudonymized with consent.

## Data availability

Anonymized conversation logs (391 sessions, 12,925 relays) are available for independent reanalysis upon reasonable request to the author, subject to privacy review. Contact: [이메일주소]

## Usage

**Browser (HTML tool):**
Open `bs-analyzer/bs_analyzer.html` in any modern browser. Load conversation logs in JSON format. The tool processes logs locally; no data is transmitted.

**Python:**

```
python bs-analyzer/bs_analyzer.py --input your_logs.json --dict bs-analyzer/bs_keywords_v22.json
```

**Adapting to your data:**
The keyword dictionary (`bs_keywords_v22.json`) externalizes all language-specific keywords, weights, and thresholds. To apply the tool to logs in a different language or with different analytical priorities, edit the dictionary file. No source code modification is needed.

## Citation

```
@article{lee2026a,
  author = {Lee, Juhyeong},
  title = {Elaboration Drift: How Human--LLM Interaction Erodes Epistemic Traction},
  year = {2026},
  note = {Preprint}
}

@article{lee2026b,
  author = {Lee, Juhyeong},
  title = {Beyond Sycophancy: Measuring Hallucination-Free Convergence in Long-Term Human--LLM Interaction},
  year = {2026},
  note = {Preprint}
}
```

## License

The analytical tools are released under the MIT License. The conversation logs and supplementary materials are provided for academic use only; redistribution is not permitted without the author's consent.

## Author

**Juhyeong Lee (이주형)**
Independent researcher
Contact: [이메일주소]
