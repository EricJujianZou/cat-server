# Talking into Claude Code

Two directions, and only one of them works today.

| Direction | State |
|---|---|
| Cat reports on Claude Code | Working. `claude-voice` profile, tested end to end. |
| Voice goes into a session | Not built. Needs a decision from you first. |

## What /voice actually is

Claude Code has a built-in voice mode. It is real, and it is not what you asked
for. Pulled from the binary:

```
/voice to enable push-to-talk dictation
Voice mode settings (hold-to-talk / tap-to-toggle dictation)
Voice mode requires a Claude.ai account. Please run /login to sign in.
Voice mode requires microphone access, but no audio device is available
Voice mode requires the native audio module (not loaded)
```

Push to talk, into the terminal you are already looking at, using the computer's
own microphone. You still hold a key and the window still has to be focused. It
replaces typing, not the window switch, so it does not solve the thing you
described.

## What the read direction does today

The `claude-voice` profile answers questions about your sessions out loud. Ask
"what is Claude doing" and it says one sentence and stops. Verified with the
device simulator: the model called the tool, got the real answer, and produced
audio.

It reads two things that Claude Code and ccpet already write for themselves:

```
~/.claude/sessions/<pid>.json               name, project, busy or idle
%LOCALAPPDATA%/ccpet/sessions/<id>.json     what the current turn is doing
```

Nothing else, no credentials, and it cannot change anything.

Separately, `tools/claude_watch.py` puts the same state on the cat's face and
speaks one line when a session is actually blocked waiting for approval. That
also works: the fake device received the `surprised` face and the sentence
"Claude needs you in cat-server" as real audio.

## Why the write direction is not built

Delivering a message into a running session on Windows means writing to that
session's named pipe, and the first line has to be an auth token. Claude Code
exports that token only to the session's own hooks and Bash commands, so an
outside process cannot get it for a session it does not belong to. A design that
had each session publish its own token to a shared file was started and then
abandoned, because handling session credentials that way is the wrong shape for
something that will eventually run on a VPS.

The sanctioned mechanism is **channels**, which exist for exactly this: pushing
external events into a running session, two way, so Claude's reply comes back
out the same path for the cat to speak. It is the right answer.

What it costs to adopt:

- Bun has to be installed. It is not on this machine.
- Channels are a research preview. A channel you write yourself is not on the
  Anthropic allowlist, so it needs `--dangerously-load-development-channels`.
- Every session you want to reach has to start with `--channels`, so it is a
  deliberate per-session opt-in rather than something ambient.

## The safety problem, which is the real reason to slow down

From the ccpet research, and it still holds: wake word false positives while
people talk in the same room are a genuine hazard, and an accidental approval in
full-auto mode is dangerous. If voice ever reaches a session, deny should be the
easy word and approve should need a confirmation. A one-word "yes" heard across
a room must never be able to approve a tool call.

## The three options, in the order I would take them

1. **Leave it read only.** The cat tells you when something needs you. You walk
   over. This is already built and has no failure mode worse than a wrong
   sentence.
2. **Channels, one session at a time.** Install Bun, write a channel that turns
   the cat's transcript into an event, launch the sessions you want reachable
   with `--channels`. Two way, sanctioned, and explicit about which sessions can
   be reached.
3. **Remote Control.** Claude Code already ships a way to drive a local session
   from a phone. If the goal is steering while away from the desk rather than
   voice specifically, this needs nothing built.
