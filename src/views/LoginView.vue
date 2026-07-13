<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useDemoStore } from '@/composables/useDemoStore';
import { CUSTOMER_EMAIL } from '@/mocks/devices';

const TYPEWRITER_SENTENCES = [
  'Device detection for overseas CGM support.',
  'Manage thresholds without changing your workflow.',
  'Detection records stay intact across every review.',
] as const;

const TYPEWRITER_CONFIG = {
  typingSpeed: 75,
  pauseDuration: 1500,
  deletingSpeed: 30,
  initialDelay: 120,
} as const;

const router = useRouter();
const store = useDemoStore();
const email = ref(CUSTOMER_EMAIL);
const password = ref('password123');
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

function login() {
  const nextEmail = email.value.trim();
  if (!store.validateAccountCredentials(nextEmail, password.value)) {
    loginError.value = 'Account or password is incorrect.';
    return;
  }
  loginError.value = '';
  store.currentUser.value = nextEmail;
  router.push('/chat');
}

onMounted(() => {
  store.ensureDefaultDetectRecords();
  startTypewriter();
});
onBeforeUnmount(clearTypewriterTimer);
</script>

<template>
  <div class="page active login-page" id="page-login">
    <div class="login-shell">
      <div class="login-shell-content">
        <section class="login-story">
          <div class="login-story-kicker">Device detection platform</div>
          <h1 class="login-display">SIBIONICS CGM AI Service Desk</h1>
          <div class="login-copy text-type" aria-live="polite">
            <span class="text-type__content">
              {{ typedLoginCopy }}
            </span>
            <span class="text-type__cursor" :class="{ 'text-type__cursor--hidden': !showTypeCursor }">|</span>
          </div>
          <div class="login-pill-row">
            <span class="login-pill">Device detection</span>
            <span class="login-pill">Thresholds</span>
            <span class="login-pill">Detection records</span>
          </div>
          <div class="login-point-list">
            <div class="login-point">
              <strong>Device detection</strong>
              <span>If you already know the user's fault type, select a card to enter device selection. If you cannot determine it yet, describe the issue to AI and it will help identify the likely fault type.</span>
            </div>
            <div class="login-point">
              <strong>Thresholds</strong>
              <span>Thresholds are condition values set by local administrators for different fault types based on after-sales policy.</span>
            </div>
            <div class="login-point">
              <strong>Detection records</strong>
              <span>Records preserve diagnostic evidence for after-sales review and track regional fault-type distribution so targeted improvement actions can be planned.</span>
            </div>
          </div>
          <div class="login-meta">Continuous Glucose Monitoring · Precision Diagnostics</div>
        </section>

        <div class="login-panel">
          <div class="login-card">
            <div class="login-brand">
              <div class="login-brand-row">
                <div class="login-logo-large">SI</div>
                <div>
                  <div class="login-eyebrow">Authorized Access</div>
                  <div class="login-title">SIBIONICS</div>
                  <div class="login-tagline">CGM AI Service Desk</div>
                </div>
              </div>
              <p class="login-intro">Sign in to continue with fault detection, threshold management, and detection-record review.</p>
            </div>
            <form class="login-form" @submit.prevent="login">
              <div class="form-group">
                <label class="form-label" for="login-email">Email Address</label>
                <div class="login-field">
                  <input id="login-email" v-model="email" class="form-input" type="email" placeholder="dealer@sibionics.com" required />
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

.login-error {
  margin: 0;
  color: #b42318;
  font-size: 0.82rem;
  font-weight: 700;
}
</style>
