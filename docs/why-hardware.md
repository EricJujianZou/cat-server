# Why hardware at all, and what the screen would have to become

The question, stated plainly: an iPhone app could do everything this cat does.
The cat has a speaker, a microphone and a small screen it barely uses. So what
is the hardware for.

The research mostly agrees with the objection. It disagrees on exactly one
point, and that one point is the entire product.

## The one thing a phone cannot do

Section 3 of `use-case-research.md` lists ten situations where a phone loses.
Nine of them are activation cost: wet hands, eyes elsewhere, a five second task
that takes thirty seconds to reach, a user who reads poorly, a child with no
phone, a shared household object with no login. Every one of those is a
convenience advantage, and a better phone UI could erode all nine.

The tenth is structural. **An app can only act once opened.** A device can start
the conversation itself, at 8am, without being remembered.

The research states the corollary bluntly, and it is worth repeating here
because it kills profiles:

> If a profile does not use the device's ability to speak first, that profile
> should be a phone app instead, and it will be a better phone app than it is a
> cat.

So the objection is correct for seven of the eight profiles as a general
statement, and wrong for the specific loop each of them is built on. The Morning
Check is the clearest case. Its user has never unlocked a phone and will not
open an app. The device works because nobody has to remember it.

## The counter-evidence, which is real

Smart speakers plateaued. Voicebot's survey of 1,000+ US adults found the top
five uses identical across January 2018, 2019 and 2020, with daily "ask a
question" use down 7.6% year on year, and only 48% of owners had ever used a
third party voice app. Japan is sharper still: MIC's FY2025 survey found smart
speaker ownership at 21.6% against actual usage at 12.4%, and the article's own
explanation for the nine point gap is that people do not know what to do with
the thing.

A general purpose assistant collapses into timers and weather. That is the
failure mode, and it is available to any device sold as an assistant rather than
as one job.

## The speaker control point

Controlling the speaker without reaching for a phone is a real advantage and it
is already built. The cat announces fourteen tools, ten of them from its own
firmware, including volume, brightness, screen theme and timers. Those work
today with nothing added on this side.

It is also, on its own, the Kitchen Cat profile, which the research ranks sixth
of eight and describes as a feature every other profile should include rather
than a product. Alexa already does it, for free, in the same room.

## The screen

Right now the screen is a mood light. The firmware draws it, the server's only
channel to it is an emoji, and the firmware maps that emoji to one of 21 faces
it already holds. The research lists this under what the device is bad at: there
is no way to show the user what it thought it heard, so a misrecognition is only
discovered after the wrong thing happens.

That is the strongest argument for a real screen. Not artwork. Confirmation.
Elderly speech transcribes at 48.3% word error rate off the shelf, and the two
top profiles are both designed around making misrecognition harmless precisely
because the device cannot show its work. A screen that displays what it heard
changes that constraint rather than decorating it.

## What reflashing would cost

Honest position: this has not been scoped against the firmware source, so what
follows is the shape of the work rather than an estimate.

The firmware is `78/xiaozhi-esp32`, MIT licensed, 138 board directories and 171
release variants. Getting custom images onto the screen needs three things that
do not exist today:

1. A protocol message for pushing image data, since the server's only screen
   channel is an emoji.
2. Display code that accepts a bitmap rather than selecting from the 21 built in
   faces.
3. A decision about bandwidth, because image data would share the same websocket
   as the audio.

The risk is not bricking. ESP32 parts have a ROM bootloader and are difficult to
permanently kill. The risk is picking the wrong one of 138 board configurations
and ending up with a device that boots to a garbled screen, a dead microphone or
no wake word, then not knowing which of the three changes caused it.

The larger cost is that reflashing removes this setup's main advantage. Nothing
here is flashed today. The cat talks to this server instead of the seller's
because the server's boot reply omits the activation block the firmware was
waiting for. No account, no soldering, no toolchain. Once the firmware is
custom, every device needs a build, and the project stops being configuration
and starts being embedded development.

## Where that leaves it

The screen is worth revisiting when a profile can name what it would display and
why speech alone fails without it. Confirmation of what was heard is the only
candidate so far that clears that bar. Artwork does not, and ccpet's poses in
particular do not, because what transfers from ccpet is the meaning rather than
the drawing, and the 21 faces already carry the meaning.

Before any of that, the cheaper experiment is to find out whether a household
uses the thing at all for six weeks. Novelty in this category decays in days to
weeks, and week six is the number that matters.
