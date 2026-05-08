<script lang="ts">
  type Status = "loading" | "ready" | "stopped" | "error";

  let {
    status = "loading",
    message = "",
    onReconnect,
    onStop,
    onStart,
    onRetry,
  }: {
    status: Status;
    message: string;
    onReconnect?: () => void;
    onStop?: () => void;
    onStart?: () => void;
    onRetry?: () => void;
  } = $props();
</script>

<div class="vm-launcher">
  <div class="status-icon">
    {#if status === "loading"}
      <div class="spinner"></div>
    {:else if status === "ready"}
      <div class="dot ready"></div>
    {:else if status === "stopped"}
      <div class="dot stopped"></div>
    {:else}
      <div class="dot error"></div>
    {/if}
  </div>

  <p class="message">{message}</p>

  <div class="actions">
    {#if status === "ready"}
      {#if onReconnect}
        <button onclick={onReconnect}>Open VM</button>
      {/if}
      {#if onStop}
        <button class="secondary" onclick={onStop}>Stop</button>
      {/if}
    {:else if status === "stopped"}
      {#if onStart}
        <button onclick={onStart}>Start VM</button>
      {/if}
    {:else if status === "error"}
      {#if onRetry}
        <button onclick={onRetry}>Retry</button>
      {/if}
    {/if}
  </div>
</div>

<style>
  .vm-launcher {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
    padding: 32px;
  }

  .status-icon {
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid rgba(255, 255, 255, 0.15);
    border-top-color: rgba(255, 255, 255, 0.8);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .dot {
    width: 16px;
    height: 16px;
    border-radius: 50%;
  }

  .dot.ready { background: #34c759; }
  .dot.stopped { background: #8e8e93; }
  .dot.error { background: #ff3b30; }

  .message {
    font-size: 14px;
    color: rgba(255, 255, 255, 0.7);
    text-align: center;
    max-width: 400px;
    word-break: break-word;
  }

  .actions {
    display: flex;
    gap: 8px;
  }

  button {
    padding: 8px 20px;
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

  button.secondary {
    background: rgba(255, 255, 255, 0.08);
  }

  button.secondary:hover {
    background: rgba(255, 255, 255, 0.15);
  }
</style>
