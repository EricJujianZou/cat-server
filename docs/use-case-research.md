# Use case research: what the xiaozhi cat should actually be

Research for turning one self-hosted server and a cheap ESP32-S3 cat into several
shipped products, each aimed at a different person. Written 2026-08-23.

Every claim that comes from a source has a URL next to it. Where a number is my
own arithmetic, or where I am guessing, the text says so. A list of things that
could not be verified is at the end of each section rather than hidden.

One methodology warning up front. This session exhausted its web search budget
partway through, so a good deal of the later verification was done by fetching
named URLs directly rather than by discovery. Coverage is strong on sources that
could be named in advance and weak on anything that needed searching for.
Southeast Asia and Latin America are the worst affected and are marked as such.

---

## 1. The device, restated as design facts

The hardware claims in the brief check out against the firmware project and the
server project.

`78/xiaozhi-esp32` (MIT, 29,106 stars, 6,725 forks, created 2024-08-31, last push
2026-08-21) supports ESP32, C3, C5, C6, S3 and P4 across **138 board directories
and 171 release variants**, does offline wake word with ESP-SR, streams Opus, and
exposes device-side MCP for speaker, LED, servo and GPIO alongside cloud-side MCP.
It ships 39 interface languages with English fallback and renders emoji
expressions on OLED or LCD. https://github.com/78/xiaozhi-esp32

`xinnan-tech/xiaozhi-esp32-server` (MIT, 10,396 stars) runs the other half. It
supports FunASR and SherpaASR locally plus OpenAI, iFlytek, Volcano, Tencent,
Alibaba and Baidu ASR over API; Qwen, DeepSeek, Zhipu, Gemini, Ollama, Dify,
FastGPT and Coze as the model; and EdgeTTS, CosyVoice, FishSpeech, GPT-SOVITS,
IndexTTS and OpenAI TTS for the voice. It also has three things the brief did not
mention and that matter enormously for this product line: **voiceprint recognition
via 3D-Speaker for multi-user identification, persistent memory through mem0ai or
PowerMem, and multi-agent management through a web console.** Minimum host for an
API-only deployment is 2 cores and 2 GB of RAM.
https://github.com/xinnan-tech/xiaozhi-esp32-server

The multi-agent console is the important one. The "several profiles, same
hardware, swap the config" plan is not something that has to be built. It is
already the shape of the upstream server.

### What the constraints mean in practice

| Constraint | Consequence for product design |
|---|---|
| One mic, far field, wake word on device | Every design must survive a room with a television in it |
| Opus over one websocket, server does everything | No wifi means no product, and there is no degraded mode |
| Firmware-drawn faces only | The screen is a mood light. It cannot confirm what was heard |
| No usable battery | It lives beside a socket, usually a counter or a bedside table |
| Server holds memory and MCP | All real capability is server side, which is also where all the cost is |
| Device MCP is volume, brightness, theme | Accessibility controls, not features |

### What it is genuinely good at

1. Turning a spoken sentence into a durable server-side state change. A reminder,
   a log entry, a message queued to a family member.
2. Speaking at the right moment without being asked. This is the only structural
   advantage the device has over a phone, and every good profile is built on it.
3. Repeating itself without irritation. People will ask a device the same question
   forty times in a week and not feel judged for it.
4. Sitting in one fixed place, which makes it a household object rather than a
   personal one. Anybody in the room can use it, with no login and no unlock.
5. Speaking a language the household speaks, in a house where nobody reads well.
6. Costing little enough to be deployed as an appliance rather than bought as a
   decision.

### What it is bad at, honestly

1. Anything involving a list. Choosing among ten options by ear is miserable.
2. Anything needing visual confirmation. There is no way to show the user what it
   thought it heard, so misrecognition is discovered only after the wrong thing
   happens.
3. Rooms with several talkers or a television. Measured accidental activation on
   commercial smart speakers runs **1.5 to 19 times per device per day**, and only
   8.44% of those triggers reproduce consistently, which means they are hard to
   engineer away.
   https://moniotrlab.khoury.northeastern.edu/publications/smart-speakers-study-pets20/
4. Anything where being wrong is expensive, because speech has no undo affordance.
5. Privacy in a shared room. Everything it says is heard by everyone present,
   including a live-in carer and any visitor.
6. Older voices. Off-the-shelf ASR on long-term-care interview speech was measured
   at **48.3% WER**, falling to 24.3% only after in-domain fine-tuning, with
   residents showing the highest error rates. https://doi.org/10.1093/jamia/ocac241
   This is the single most under-appreciated risk in every eldercare profile below.
7. Non-English wake words. Espressif's WakeNet ships Chinese, English, Japanese
   and French only, with "Bonjour ESP" as the sole European option beyond English.
   A custom wake word needs **20,000+ audio samples from 500+ speakers** plus a
   paid Espressif engagement running two to three weeks after corpus collection.
   https://docs.espressif.com/projects/esp-sr/en/latest/esp32s3/wake_word_engine/README.html
   https://docs.espressif.com/projects/esp-sr/en/latest/esp32s3/wake_word_engine/ESP_Wake_Words_Customization.html
8. Emergencies. It is useless the moment the internet or the power goes.

### The cost problem that decides everything

A voice agent assembled from raw APIs costs roughly **USD 0.007 to 0.091 per
conversation minute** at July 2026 prices.
https://inworld.ai/resources/voice-agent-cost-per-minute-2026
OpenAI's own list: gpt-4o-mini-transcribe $0.003/min, Whisper $0.006/min,
gpt-4o-mini-tts about $0.015/min of generated audio, gpt-realtime-2.1 at $32/1M
audio input and $64/1M audio output tokens.
https://developers.openai.com/api/docs/pricing

My arithmetic, flagged as derived rather than sourced: a cascaded pipeline of
transcription plus a text model plus TTS costs about **$0.015 to $0.02 per
conversation minute**. Ten minutes of use a day is **$4.50 to $6 per device per
month**, and a flagship realtime model is roughly $15.

Set that against a $20-50 device. The hardware pays for somewhere between four and
ten days of heavy conversation before the API bill exceeds the entire retail price.
This is the arithmetic that killed Moxie, and it explains why every surviving
competitor either charges a subscription (ElliQ at $39-59/month, Romi at
JPY 1,780/month for conversation at all, Sharp's Pokétomo metering conversations
at JPY 495 for 400 of them) or ships a device that is not conversational.

**No profile in this document is viable without a stated answer to who pays the
inference bill.** That answer is either a subscription, an institution, or a hard
per-day conversation cap enforced server side.

---

## 2. Optimising for non-developer users

The owner is a developer, and the developer profile is the one that will feel most
obvious. It should be built last, or never shipped.

### The case against the developer profile

The strongest developer use case is voice approval of a coding agent's permission
prompts, which removes a window switch from a loop that gets hit dozens of times a
day. It is real, and it is genuinely the best fit for hands-free input while
looking somewhere else. It also has a total addressable market of roughly one
household, competes with a keyboard shortcut that costs nothing, and carries a
specific danger, which is that an accidental wake-word approval in a full-auto
session is an unrecoverable action taken by a false positive. Keep it as the
owner's own configuration. Do not count it as a profile.

### The people whose day actually gets better

The common factor across all of them is that the cost of getting to a phone app
exceeds the value of the task.

- **An 80 year old living alone** whose children are in another city or another
  country. In Italy that is 31.7% of over-65s, and almost 40% of over-75s.
- **The adult daughter managing a parent's medication from a distance.** She is the
  buyer, and the parent is the user. This split matters more than anything else in
  the eldercare profiles.
- **A parent of a four to eight year old** who wants the child learning without
  handing over a screen. Tonies built a EUR 630 million business on exactly this
  instinct, with no AI in the product at all.
- **A woman in a household who does not own the household phone.** In India 84% of
  men own a mobile phone against 56% of women, and much of women's access is to a
  shared family device. https://www.gsma.com/gender-gap-2025/
- **A person who cooks for a family every day** and whose hands are wet for two
  hours of it.
- **A migrant worker's child** being raised by grandparents, where the parent is
  the one who wants a channel into the house.
- **A person who speaks fluently and reads badly.** In rural India 89.1% of 14-16
  year olds have a smartphone at home and 82.2% can operate one, while only 27.1%
  of Std III children can read a Std II level text.
  https://asercentre.org/wp-content/uploads/2022/12/India.pdf
- **A live-in carer** who needs to hand over information to the next shift or to
  the family, and who often does not share a first language with the household.
  In Italy roughly 70% of the 817,000 registered domestic workers are foreign.

### The buyer is usually not the user

For every eldercare and childcare profile, the person paying is an adult child or
a parent, and the person talking to the cat is not. This has three consequences.
The pitch has to be legible to the buyer in one sentence. The measurable outcome
has to be visible to the buyer without asking the user. And the setup has to be
completable by the buyer remotely, because they are not in the room.

---

## 3. Where an always-on ambient device beats a phone app

The phone is more capable in every technical dimension. It loses on activation
cost, and it loses completely on one thing it structurally cannot do.

| Situation | Why the phone loses |
|---|---|
| Hands wet or full | Unlocking needs a dry finger or a face at the right angle |
| Eyes on something else | Reading means looking away from the pan, the child, the road |
| The user reads poorly | Every app is a reading test before it is a tool |
| The task is five seconds long | Finding the app costs thirty |
| The user is a child | No phone, or a phone the parent will not hand over |
| Elderly and the UI is the barrier | Among homebound older adults, 82% report uncertainty about how to use devices, 68.9% are unfamiliar with the options, and 50.8% report discomfort learning new things (https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12761175/) |
| The device must be visible to a room | A phone in a pocket cannot prompt anyone else |
| Nothing may be unlocked | Shared household object, no account, no password |
| Nobody in the house owns a phone of their own | Shared-device households, common across South Asia |
| **The prompt has to arrive unbidden** | **An app can only act once opened** |

The last row is the whole argument. A phone app is a place the user has to decide
to go. An always-on device can start the conversation itself, at 8am, without
being remembered. Everything else in this table is a convenience advantage that a
better phone UI could erode. That one is structural.

The corollary is uncomfortable and worth stating. If a profile does not use the
device's ability to speak first, that profile should be a phone app instead, and
it will be a better phone app than it is a cat.

### The counter-evidence, which is real

Smart speakers plateaued because their use cases never broadened. Voicebot's survey
of 1,000+ US adults found the top five uses identical in January 2018, 2019 and
2020, with daily "ask a question" use **down 7.6% year on year**, and only 48% of
owners had ever used a third party voice app.
https://voicebot.ai/2020/05/03/streaming-music-questions-weather-timers-and-alarms-remain-smart-speaker-killer-apps-third-party-voice-app-usage-not-growing/
ComScore's use frequencies were basic questions 60%, weather 57%, music 54%,
timers and alarms 41%.
https://www.idownloadblog.com/2017/05/31/comscore-survey-smart-speaker-use-cases/

Japan shows the failure mode even more sharply. MIC's FY2025 survey (n=1,800,
fielded 2025-12-01 to 12-07) found smart speaker **ownership at 21.6% but actual
usage at 12.4%**. The article's own explanation for the nine point gap is that
people do not know what to do with the thing.
https://news.yahoo.co.jp/expert/articles/395af532beba8a244971fa6b21322745b3678b2d

There is also a meta-analysis that should temper the companionship pitch
specifically: Hansen et al. 2025, 40 RCTs, N=6,062, found robotic pets reduced
loneliness while **conversational robots showed limited impact**.
DOI 10.1016/j.invent.2025.100856

The lesson from all of this is that a general purpose assistant collapses into
timers and weather. A device with one job, that speaks first, and that a specific
person has been given for a specific reason, does not have that failure mode
available to it.
