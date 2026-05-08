<script lang="ts">
  let { onRetry }: { onRetry: () => void } = $props();
</script>

<div class="docker-missing">
  <div class="icon">
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <rect x="2" y="6" width="20" height="12" rx="2"/>
      <path d="M6 10h2v4H6z M10 10h2v4h-2z M14 10h2v4h-2z"/>
    </svg>
  </div>
  <h2>Docker Not Found</h2>
  <p>Inspekt Browser VM requires Docker or OrbStack to run.</p>
  <p class="hint">Install <a href="https://orbstack.dev" target="_blank">OrbStack</a> (recommended) or <a href="https://docker.com" target="_blank">Docker Desktop</a>, then try again.</p>
  <button onclick={onRetry}>Retry</button>
</div>

<style>
  .docker-missing {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    padding: 32px;
    text-align: center;
  }

  .icon {
    color: rgba(255, 255, 255, 0.4);
    margin-bottom: 8px;
  }

  h2 {
    font-size: 18px;
    font-weight: 600;
    color: white;
    margin: 0;
  }

  p {
    font-size: 14px;
    color: rgba(255, 255, 255, 0.6);
    margin: 0;
    max-width: 360px;
  }

  .hint {
    font-size: 13px;
    color: rgba(255, 255, 255, 0.4);
  }

  a {
    color: rgba(100, 180, 255, 0.9);
    text-decoration: none;
  }

  a:hover {
    text-decoration: underline;
  }

  button {
    margin-top: 8px;
    padding: 8px 24px;
    border-radius: 8px;
    border: none;
    background: rgba(255, 255, 255, 0.15);
    color: white;
    font-size: 13px;
    cursor: pointer;
  }

  button:hover {
    background: rgba(255, 255, 255, 0.25);
  }
</style>
