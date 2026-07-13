<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useDemoStore } from '@/composables/useDemoStore';

const TYPEWRITER_SENTENCES = [
  'Device Detection for overseas CGM support.',
  'Manage thresholds without changing your workflow.',
  'Detection History stays intact across every review.',
] as const;

const TYPEWRITER_CONFIG = {
  typingSpeed: 75,
  pauseDuration: 1500,
  deletingSpeed: 30,
  initialDelay: 120,
} as const;

const router = useRouter();
const store = useDemoStore();
const email = ref('');
const password = ref('');
const typedLoginCopy = ref('');
const showTypeCursor = ref(true);
const loginError = ref('');
let typewriterTimer: number | undefined;

function clearTypewriterTimer() {
  if (typewriterTimer !== undefined) {
    window.clearTimeout(typewriterTimer);
    typewriterTimer = undefined;
  }
}

function startTypewriter() {
  clearTypewriterTimer();

  const reduceMotion = typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  if (reduceMotion) {
    typedLoginCopy.value = TYPEWRITER_SENTENCES[0];
    showTypeCursor.value = false;
    return;
  }

  let currentTextIndex = 0;
  let currentCharIndex = 0;
  let isDeleting = false;

  typedLoginCopy.value = '';
  showTypeCursor.value = true;

  function tick() {
    const sentence = TYPEWRITER_SENTENCES[currentTextIndex];

    if (!isDeleting && currentCharIndex < sentence.length) {
      currentCharIndex += 1;
      typedLoginCopy.value = sentence.slice(0, currentCharIndex);
      typewriterTimer = window.setTimeout(tick, TYPEWRITER_CONFIG.typingSpeed);
      return;
    }

    if (!isDeleting && currentCharIndex === sentence.length) {
      isDeleting = true;
      typewriterTimer = window.setTimeout(tick, TYPEWRITER_CONFIG.pauseDuration);
      return;
    }

    if (isDeleting && currentCharIndex > 0) {
      currentCharIndex -= 1;
      typedLoginCopy.value = sentence.slice(0, currentCharIndex);
      typewriterTimer = window.setTimeout(tick, TYPEWRITER_CONFIG.deletingSpeed);
      return;
    }

    isDeleting = false;
    currentTextIndex = (currentTextIndex + 1) % TYPEWRITER_SENTENCES.length;
    typewriterTimer = window.setTimeout(tick, TYPEWRITER_CONFIG.initialDelay);
  }

  typewriterTimer = window.setTimeout(tick, TYPEWRITER_CONFIG.initialDelay);
}

async function login() {
  const nextEmail = email.value.trim();
  if (!await store.loginRemote(nextEmail, password.value)) {
    loginError.value = 'Account or password is incorrect.';
    return;
  }
  loginError.value = '';
  router.push('/chat');
}

onMounted(() => {
  if (!store.backendOnline.value) store.ensureDefaultDetectRecords();
  startTypewriter();
});
onBeforeUnmount(clearTypewriterTimer);
</script>

<template>
  <div class="page active login-page" id="page-login">
    <div class="login-shell">
      <div class="login-shell-content">
        <section class="login-story">
          <div class="login-story-kicker">Device Detection platform</div>
          <h1 class="login-display">SIBIONICS CGM AI Service Desk</h1>
          <div class="login-copy text-type" aria-live="polite">
            <span class="text-type__content">
              {{ typedLoginCopy }}
            </span>
            <span class="text-type__cursor" :class="{ 'text-type__cursor--hidden': !showTypeCursor }">|</span>
          </div>
          <div class="login-pill-row">
            <span class="login-pill">Device Detection</span>
            <span class="login-pill">Thresholds</span>
            <span class="login-pill">Detection History</span>
          </div>
          <div class="login-point-list">
            <div class="login-point">
              <strong>Device Detection</strong>
              <span>If you know the issue type, select a card to choose your device. If you are unsure, describe the problem to AI, and it will help identify possible issues.</span>
            </div>
            <div class="login-point">
              <strong>Thresholds</strong>
              <span>Thresholds are criteria values set by local administrators for different issue types according to after-sales service policies.</span>
            </div>
            <div class="login-point">
              <strong>Detection History</strong>
              <span>Records are saved as diagnostic evidence for after-sales review, and track the distribution of issue types across regions to support targeted improvement planning.</span>
            </div>
          </div>
          <div class="login-meta">Continuous Glucose Monitoring · Precision Diagnostics</div>
        </section>

        <div class="login-panel">
          <div class="login-card">
            <div class="login-brand">
              <div class="login-brand-row">
                <div class="login-brand-mark">
                  <img src="/favicon.png" alt="SIBIONICS"/>
                </div>
                <div class="login-brand-text">
                  <div class="login-eyebrow">Authorized Access</div>
                  <div class="login-title">SIBIONICS</div>
                  <div class="login-tagline">CGM AI Service Desk</div>
                </div>
              </div>
              <p class="login-intro">Sign in to continue to fault detect, threshold governance, and detect-record review.</p>
              <p class="login-intro"></p>
            </div>
            <form class="login-form" @submit.prevent="login">
              <div class="form-group">
                <label class="form-label" for="login-email">Account</label>
                <div class="login-field">
                  <input id="login-email" v-model="email" class="form-input" type="text" placeholder="christest@sibionics.com" required />
                </div>
              </div>
              <div class="form-group">
                <label class="form-label" for="login-password">Password</label>
                <div class="login-field">
                  <input id="login-password" v-model="password" class="form-input" type="password" placeholder="Enter password" required />
                </div>
              </div>
              <p v-if="loginError" class="login-error" data-test="login-error">{{ loginError }}</p>
              <button class="btn btn-primary btn-lg" type="submit">Sign In</button>
            </form>
            <div class="login-footer">
              <span>Continuous Glucose Monitoring · Precision Diagnostics</span>
              <span>&copy; 2026 SIBIONICS Technology Co., Ltd.</span>
            </div>
            <div class="login-decoration"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
#login-password {
  font-family: Arial, sans-serif;
  letter-spacing: 0;
}

/* ── Login brand — icon independent from text ── */
.login-brand {
  margin-bottom: 4px;
}

.login-brand-row {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.login-brand-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 96px;
  height: 96px;
  border-radius: 28px;
  background: linear-gradient(
    150deg,
    rgba(255, 255, 255, 0.55) 0%,
    rgba(255, 255, 255, 0.12) 100%
  );
  border: 1px solid rgba(255, 255, 255, 0.45);
  -webkit-backdrop-filter: blur(6px);
  backdrop-filter: blur(6px);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.7),
    0 8px 24px rgba(0, 0, 0, 0.05);
}

.login-brand-mark img {
  width: 56px;
  height: 56px;
  object-fit: contain;
}

.login-brand-text {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.login-error {
  margin: 0;
  color: #b42318;
  font-size: var(--text-xs);
  font-weight: 700;
}

@media (max-width: 480px) {
  .login-card {
    padding: var(--card-padding);
    width: 100%;
    border-radius: var(--radius-lg);
  }

  .login-page .login-shell {
    padding: var(--page-padding);
  }

  .login-page .login-copy {
    font-size: var(--text-sm);
  }
}
</style>
