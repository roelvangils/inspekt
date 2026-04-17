<script lang="ts">
  import { onMount } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { listen } from "@tauri-apps/api/event";
  import VmLauncher from "$lib/components/VmLauncher.svelte";
  import DockerMissing from "$lib/components/DockerMissing.svelte";

  type AppState = "checking" | "docker-missing" | "starting" | "ready" | "error" | "stopped";

  let state: AppState = $state("checking");
  let statusMessage = $state("Checking system requirements…");
  let errorMessage = $state("");

  async function checkAndStart() {
    state = "checking";
    statusMessage = "Checking Docker…";

    try {
      const dockerOk = await invoke<boolean>("check_docker");

      if (!dockerOk) {
        state = "docker-missing";
        return;
      }

      // Check if VM is already running and healthy
      const status = await invoke<{
        dockerRunning: boolean;
        containerRunning: boolean;
        healthOk: boolean;
      }>("check_vm_status");

      if (status.containerRunning && status.healthOk) {
        statusMessage = "VM is running. Opening…";
        await invoke("open_vm_window");
        state = "ready";
        return;
      }

      // Start the VM
      state = "starting";
      statusMessage = "Starting VM…";
      await invoke("start_vm");
    } catch (err) {
      state = "error";
      errorMessage = String(err);
    }
  }

  function handleRetry() {
    errorMessage = "";
    checkAndStart();
  }

  async function handleStop() {
    statusMessage = "Stopping VM…";
    state = "starting";
    try {
      await invoke("stop_vm");
      state = "stopped";
    } catch (err) {
      state = "error";
      errorMessage = String(err);
    }
  }

  onMount(() => {
    // Listen for Tauri events from the Rust backend
    listen<string>("vm-progress", (event) => {
      statusMessage = event.payload;
    });

    listen<string>("vm-ready", async () => {
      statusMessage = "VM is ready. Opening…";
      try {
        await invoke("open_vm_window");
        state = "ready";
      } catch (err) {
        state = "error";
        errorMessage = String(err);
      }
    });

    listen<string>("vm-error", (event) => {
      state = "error";
      errorMessage = event.payload;
    });

    listen("vm-stopped", () => {
      state = "stopped";
    });

    // Start the check
    checkAndStart();
  });
</script>

<div class="launcher" data-tauri-drag-region>
  {#if state === "docker-missing"}
    <DockerMissing onRetry={handleRetry} />
  {:else if state === "ready"}
    <VmLauncher
      status="ready"
      message="VM is running"
      onReconnect={() => invoke("open_vm_window")}
      onStop={handleStop}
    />
  {:else if state === "stopped"}
    <VmLauncher
      status="stopped"
      message="VM is stopped"
      onStart={handleRetry}
    />
  {:else if state === "error"}
    <VmLauncher
      status="error"
      message={errorMessage}
      onRetry={handleRetry}
    />
  {:else}
    <VmLauncher
      status="loading"
      message={statusMessage}
    />
  {/if}
</div>

<style>
  .launcher {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    /* Allow dragging the window from the background */
  }
</style>
