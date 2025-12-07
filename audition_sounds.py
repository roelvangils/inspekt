#!/usr/bin/env python3
"""
Temporary script to audition sound variations for Inspekt.

Run this script, then note your preferred sound (1-5) for each action.
After auditioning, update replay_visual.js with your chosen sounds.

Usage:
    python audition_sounds.py

Make sure:
1. The Chrome extension is running
2. You have a browser tab open
3. Click in the browser window when prompted (to unlock audio)
"""

import json
import time
import sys
from pathlib import Path

# Add inspekt to path
sys.path.insert(0, str(Path(__file__).parent))

from inspekt.client import BridgeClient

# All action types (grouped logically)
ACTIONS = [
    # Session sounds (TRITONES - 3 notes)
    "start_recording",
    "stop_recording",
    "start_playback",
    "stop_playback",
    # Action sounds (SINGLETONES / DUOTONES only)
    "navigate",
    "click",
    "rightclick",
    "activate",
    "type",
    "keypress",
    "hover",
    "check",
    "uncheck",
    "radio",
    "select",
    "scroll",
    "plugin",
    "inspekt",
    "failure",
]

# Descriptions for context
DESCRIPTIONS = {
    # Session sounds (tritones - 3 notes)
    "start_recording": "Beginning recording session [TRITONE - 3 ascending notes]",
    "stop_recording": "Ending recording session [TRITONE - 3 descending notes]",
    "start_playback": "Beginning replay [TRITONE - 3 ascending notes, different from recording]",
    "stop_playback": "Ending replay [TRITONE - 3 descending notes, different from recording]",
    # Action sounds (singletones/duotones)
    "navigate": "Page navigation [SWEEP - ascending frequency sweep]",
    "click": "Mouse click [CLICK - tick + thump variations]",
    "rightclick": "Context menu click [CLICK variant - deeper/different]",
    "activate": "Enter/Space activation [DING - confirmation tone]",
    "type": "Typing text [KEYBOARD - clack/tactile sound]",
    "keypress": "Keyboard shortcut [KEY - spacebar/modifier key sound]",
    "hover": "Mouse hover [WHOOSH - gentle breeze/wind sound]",
    "check": "Checkbox checked [ASCENDING duo - positive confirmation]",
    "uncheck": "Checkbox unchecked [DESCENDING duo - reverse of check]",
    "radio": "Radio button [PING/DUO - exclusive selection tone]",
    "select": "Dropdown selection [DUO - selection blip]",
    "scroll": "Page scroll [SLIDE - soft descending sweep]",
    "plugin": "Running plugin [BLOOP-BLOOP - identical double tone]",
    "inspekt": "Running inspekt [BLEEP-BLEEP - identical double tone, higher pitch]",
    "failure": "Action failed [DISSONANT - error/warning buzz]",
}


def main():
    print("\n" + "=" * 60)
    print("  INSPEKT SOUND AUDITION")
    print("=" * 60)
    print("\nThis script will play 5 sound variations for each action.")
    print("Write down your preferred sound (1-5) for each action.\n")

    # Connect to browser
    print("Connecting to browser...")
    client = BridgeClient()

    # Load the audition script
    script_path = Path(__file__).parent / "inspekt" / "scripts" / "sound_audition.js"
    if not script_path.exists():
        print(f"Error: Could not find {script_path}")
        sys.exit(1)

    script_content = script_path.read_text()

    print("Loading sound audition script into browser...")
    result = client.execute(script_content, timeout=5.0)

    # Check for successful load - result is nested in response
    loaded = result.get("loaded") or (result.get("result", {}).get("loaded"))
    if not loaded:
        print(f"Error loading script: {result}")
        sys.exit(1)

    print("Script loaded successfully!")
    print("\n" + "-" * 60)
    print("IMPORTANT: Click anywhere in your browser window NOW")
    print("to unlock audio playback (browser autoplay policy).")
    print("-" * 60)
    input("\nPress Enter after clicking in the browser...")

    # Resume audio context
    client.execute("window.__INSPEKT_SOUND_AUDITION__.resume();", timeout=2.0)

    print("\n" + "=" * 60)
    print("  STARTING AUDITION")
    print("=" * 60)

    # Track choices
    choices = {}

    for action in ACTIONS:
        print(f"\n{'=' * 60}")
        print(f"  ACTION: {action.upper()}")
        print(f"  {DESCRIPTIONS.get(action, '')}")
        print("=" * 60)

        input(f"\nPress Enter to hear 5 sounds for '{action}'...")

        for variation in range(1, 6):
            print(f"\n  Playing sound {variation} of 5...", end=" ", flush=True)

            result = client.execute(
                f"window.__INSPEKT_SOUND_AUDITION__.play('{action}', {variation});",
                timeout=2.0
            )

            if result.get("ok"):
                print("OK")
            else:
                print(f"Error: {result.get('error', 'Unknown')}")

            time.sleep(1.5)  # Wait between sounds

        # Ask for choice
        while True:
            choice = input(f"\n  Your choice for '{action}' (1-5, or 'r' to replay): ").strip().lower()

            if choice == 'r':
                print("\n  Replaying all 5 sounds...")
                for variation in range(1, 6):
                    print(f"    Sound {variation}...", end=" ", flush=True)
                    client.execute(
                        f"window.__INSPEKT_SOUND_AUDITION__.play('{action}', {variation});",
                        timeout=2.0
                    )
                    print("OK")
                    time.sleep(1.5)
            elif choice in ['1', '2', '3', '4', '5']:
                choices[action] = int(choice)
                print(f"  Recorded: {action} = sound {choice}")
                break
            else:
                print("  Please enter 1-5, or 'r' to replay")

    # Summary
    print("\n" + "=" * 60)
    print("  YOUR CHOICES")
    print("=" * 60)
    print()

    for action in ACTIONS:
        choice = choices.get(action, "?")
        print(f"  {action:20} : sound {choice}")

    # Save to file
    choices_file = Path(__file__).parent / "sound_choices.json"
    with open(choices_file, "w") as f:
        json.dump(choices, f, indent=2)

    print("\n" + "-" * 60)
    print(f"Choices saved to: {choices_file}")
    print("-" * 60)
    print("\nYou can now run the implementation step to update")
    print("replay_visual.js with your chosen sounds.")


if __name__ == "__main__":
    main()
