Inspekt reads configuration from *~/.config/inspekt.json* (created on first
run with **inspekt config**). Frequently used settings include:

**ai-language**
:   Preferred natural-language for AI commands such as **inspekt summarize**
    and **inspekt describe** ("auto" detects from the page).

**bridge-port**
:   TCP port the bridge server listens on (default 8888). The same port is
    used by the browser extension to connect.

Run **inspekt config** to open the file in your default editor; **inspekt
info config** prints the active configuration with sources.
