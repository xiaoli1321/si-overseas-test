# SIBIONICS CGM AI servdesk Prototype PRD

## Current Scope

The prototype supports overseas CGM after-sales detect workflows through three main areas:

| Route | View | Purpose |
| --- | --- | --- |
| `/` | Login | Demo account sign-in |
| `/chat` | AgentChat | AI-assisted fault-type recommendation |
| `/fault-query/:categoryKey` | FaultQuery | Same-fault SN lookup, selected devices, and multi-device results |
| `/detect/:sn` | DetectFlow | Single-device evidence review, processing, and verdict |
| `/multi-detect/:batchId` | MultiDetect | Same-fault multi-device processing and results |
| `/records` | DetectRecords | Historical detect records and filtering |
| `/thresholds` | Thresholds | Data accuracy rule profile governance |
| `/accounts` | AccountManagement | Dealer manager staff account management |

`/detect` redirects to `/chat`. There is no standalone Batch Query or legacy bulk flow.

## Device Detect Flow

Users start from either a homepage fault card or an AI recommended fault card. Both routes enter `FaultQueryView` with a fixed fault type.

In `FaultQueryView`, users can add devices by:

- Pasting a full SN, which is added directly when it matches one device.
- Searching an SN fragment, which shows matching candidates for selection.
- Pasting multiple lines, where unique matches are added and ambiguous or missing lines stay in a pending-confirmation area.

All selected devices run under the current fault type. The user does not choose a different fault type per device.

## Multi-Device Results

When one device is selected, the user continues into the single-device detect page.

When multiple devices are selected, `FaultQueryView` creates a grouped run and navigates to `MultiDetectView`:

- Each device creates a `DetectSession` with `source: 'multi'`.
- All sessions in the same submission share one `batchId`.
- Each completed device writes one `DetectRecord`.
- Every generated record uses the fixed fault category from the current `categoryKey`.

## Session Manager

`AppShell` groups detect sessions before rendering them:

- Single-device sessions remain one row per session.
- Multi-device sessions group by `batchId + faultCategory`.
- Processing groups show device count and completed count, such as `Sensor falling off · 2 devices · 1/2 complete`.
- Completed groups show record count and can return to the same `FaultQueryView` result context or open Detect records.

The toolbar count reflects grouped sessions, not raw device-session rows.

## Implementation Notes

Core implementation files:

- `src/views/AgentChatView.vue`
- `src/views/FaultQueryView.vue`
- `src/components/layout/AppShell.vue`
- `src/composables/useDemoStore.ts`
- `src/types/record.ts`

Removed legacy surfaces:

- Standalone Batch Query modal in chat.
- Legacy standalone bulk route.
- `BatchDetectView`.
- `FaultDetectView`.
