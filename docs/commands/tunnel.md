# inspekt tunnel

Expose a local port to the Inspekt Browser VM.

## Synopsis

```bash
inspekt tunnel <PORT> [OPTIONS]
```

## Description

Creates a secure tunnel from your local machine to the Inspekt Browser VM, making your local development server accessible from within the VM's browser. This is essential when the VM runs in the cloud.

The command uses [bore](https://github.com/ekzhang/bore) as the tunnel transport. The bore client is automatically downloaded on first use.

## Arguments

| Argument | Description |
|----------|-------------|
| `PORT` | The local port to expose (required) |

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--host HOST` | VM host address | `localhost` (local VM) |
| `--secret SECRET` | Tunnel authentication secret | Auto-detected from VM |
| `--remote-port PORT` | Port on the VM side | Same as local port |
| `-v, --verbose` | Show detailed connection info | Off |

## Examples

### Basic usage

Expose your local dev server running on port 3000:

```bash
inspekt tunnel 3000
```

### Cloud VM

Connect to a remote VM:

```bash
inspekt tunnel 3000 --host vm.example.com
```

### Different remote port

Map local port 3000 to port 8080 inside the VM:

```bash
inspekt tunnel 3000 --remote-port 8080
```

### Manual secret

Provide the tunnel secret explicitly:

```bash
inspekt tunnel 3000 --host vm.example.com --secret mysecrettoken
```

## How it works

1. Checks if the local port is listening (warns if not)
2. Downloads the bore client binary if not already installed
3. Fetches the tunnel secret from the VM's control server (`/api/tunnel-info`)
4. Establishes a bore tunnel connection
5. Keeps running until you press Ctrl+C

## See also

- [Tunneling Guide](../guide/tunneling.md) — Detailed explanation of the tunnel architecture
- [inspekt vm](vm.md) — Managing the Browser VM
