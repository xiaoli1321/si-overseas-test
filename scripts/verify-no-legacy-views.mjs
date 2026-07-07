import { existsSync, rmSync } from 'node:fs';
import { join } from 'node:path';

const legacyPaths = [
  'src/views/BatchDiagnosisView.vue',
  'src/views/BatchDiagnosisView.test.ts',
  'src/views/DiagnosisFlowView.vue',
  'src/views/DiagnosisFlowView.test.ts',
  'src/views/DiagnosisFlowView.vue.js',
  'src/views/FaultCategorySelectionView.vue',
  'src/views/FaultCategorySelectionView.test.ts',
  'src/views/FaultDetectView.vue',
  'src/views/FaultDetectView.test.ts',
  'src/views/FaultDetectView.vue.js',
  'src/components/diagnosis',
];

const removed = [];

for (const relativePath of legacyPaths) {
  const absolutePath = join(process.cwd(), relativePath);
  if (!existsSync(absolutePath)) continue;

  rmSync(absolutePath, { recursive: true, force: true });
  removed.push(relativePath);
}

if (removed.length) {
  console.warn('Removed legacy diagnosis views before build:');
  for (const file of removed) console.warn(`  - ${file}`);
}
