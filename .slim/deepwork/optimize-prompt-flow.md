# Optimize Overseas Prompt Flow

## Status: Phase 2 Complete — Phase 3 (Review) Done. Ready to merge.

## Architecture Comparison

### Chinese Version (si-mcp GS1)
```
detector (multi-class) → judger (per-category polling) → storyteller
```
- Rich business background: assembly process, component descriptions
- Detailed scenario few-shots: description, core cause, judgment conditions, responsibility
- Explicit scoring guidelines (0-1/2-5/6-7/8-9/10)
- Negative discrimination rules for specific scenarios

### Overseas Version (after optimization)
```
scenario evaluation (parallel per-category) → arbitration
```
- Enriched scenario definitions with core_cause, judgment_conditions, responsibility
- Scoring guidelines in calibration block
- Negative discrimination for early_launches
- Arbitration template also updated with new fields

## Changes Made

### Phase 2a: Enriched DEFAULT_FAULT_SCENARIOS
- Added `core_cause` (核心原因) to all 6 scenarios
- Added `judgment_conditions` (判断条件) to all 6 scenarios
- Added `negative_discrimination` (不属于当前小类的情况) to `early_launches`
- Added `responsibility` (判责分类) to all 6 scenarios

### Phase 2b: Scoring Guidelines
- Added 置信度评分范围 to `base.jinja2` calibration block (0-1/2-5/6-7/8-9/10)

### Phase 2c: Template Updates
- `scenario_system_prompt.jinja2`: Renders core_cause, judgment_conditions, responsibility, negative_discrimination
  - All new fields wrapped in `{% if %}` guards for empty-safe rendering
  - Removed redundant `positive_rules` rendering (covered by judgment_conditions)
- `arbitration_system_prompt.jinja2`: Now includes core_cause, judgment_conditions, negative_discrimination
- `build_system_prompt` and `build_arbitration_system_prompt` pass new fields to templates

### Fixed (from Oracle review):
- 🔴 **Bug**: `negative_discrimination` block was silently dropped (child-only block)
- 🔴 **Missing**: Added `responsibility` field to scenarios
- 🟡 **Quality**: Wrapped all new fields in `{% if %}` guards
- 🟡 **Quality**: Removed `positive_rules` from per-scenario template to reduce redundancy
- 🟡 **Quality**: Updated arbitration template with new fields

## Not Done (deferred per plan)
- Business background (assembly process) — still in Chinese reference, not ported
- Product structure descriptions with images — not yet added
- Pipeline merge (QwenVlClient + ImplantationScanner) — large separate refactor
- Dead code removal (arbitrate_results) — code quality, not prompt flow

## Verification
- All 45 non-DB backend tests pass
- All 141 frontend tests pass
- Frontend builds successfully (vue-tsc + vite)
