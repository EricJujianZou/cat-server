# ccpet on the cat

You asked whether ccpet's pictures and sounds could go on the cat's screen. The
pictures cannot. The states can, and they do.

## Why the artwork does not transfer

The cat's screen is drawn by its own firmware, not by the server. The server's
only screen channel is an emoji, and the firmware maps that emoji to one of 21
faces it already holds. Nothing else reaches the screen in normal operation.

The full list is in `config/README.md`. ccpet's own poses have no equivalent
there, so what transfers is the meaning rather than the drawing.

There may be a way around this that does not need a reflash. The v2 firmware
holds two tools it hides from the model, one that draws an image from a URL and
one that swaps the whole emoji set, and both are reachable over the socket the
cat already holds. Whether this vendor build kept them is a one command check.
See [pictures-on-the-screen.md](pictures-on-the-screen.md).

## The mapping

| ccpet state | ccpet pose | Cat face |
|---|---|---|
| waiting | needs-you | 😲 surprised |
| error | error | 😔 sad |
| done | done, feet up with noodles | 🤤 delicious |
| asleep | asleep | 😴 sleepy |
| thinking, reading, editing, searching, running, delegating | the working family | 🤔 thinking |

`delicious` for done is the closest the firmware gets to the instant noodles,
which is the one pose in ccpet with a specific joke in it.

## Sound

ccpet ships no audio files, so there is nothing to play. The cat speaks instead,
which is better anyway: a tone tells you something happened, a sentence tells
you what. It says one line, only on the state worth interrupting someone for.

> Claude needs you in cat-server.

`--say-all` extends that to done and error. `--silent` turns the face on and the
voice off.

## Running it

```powershell
.\cat.ps1 watch     # starts this and the status agent, detached
.\cat.ps1 status    # says whether both are up
.\cat.ps1 unwatch   # stops them
```

To run it in the foreground and watch it work, or to change what it says out
loud:

```powershell
py -3.13 tools\claude_watch.py            # face, and speaks on waiting
py -3.13 tools\claude_watch.py --say-all  # also speaks on done and error
py -3.13 tools\claude_watch.py --dry-run  # prints what it would push
```

Use a real CPython rather than whatever `python` resolves to. On this machine
`python` is the MSYS2 build, which cannot read Windows process state.

It reuses ccpet's own rule for which session wins when several are running,
including the staleness timeouts and louder-beats-busier, so the cat and the pet
never disagree about what is happening.

## What it needs

The push bridge, which is the two mounted files in `patches/`, and a cat
connected. With the hardware off, `python3 tools/fake_cat.py --listen` stands in
and prints everything the server sends.

Verified this way: the state changed to waiting, the fake device received the
`surprised` face and then 34 frames of Opus audio saying the line.
