# Use case research: what the xiaozhi cat should actually be

Research for turning one self-hosted server and a cheap ESP32-S3 cat into several
shipped products, each aimed at a different person. Written 2026-08-23.

Every claim that comes from a source has a URL next to it. Where a number is my
own arithmetic, or where I am guessing, the text says so. A list of things that
could not be verified is at the end of each section rather than hidden.

One methodology warning up front. This session exhausted its web search budget
partway through, so a good deal of the later verification was done by fetching
named URLs directly rather than by discovery. Coverage is strong on sources that
could be named in advance and weaker on anything that needed searching for. Every
region named in the brief was researched.

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

---

## 4. Global market, region by region

Two constraints filter every market before anything cultural matters. The device
needs **home wifi**, and it needs **continuous mains power**. Both are scarcer than
a developer in a rich country assumes.

For scale: ITU's Facts and Figures 2025 reports almost three quarters of the world
population online, 2.2 billion still offline, over four in five people owning a
mobile phone, and one in three economies still failing the affordability target.
https://www.itu.int/itu-d/reports/statistics/facts-figures-2025/

### Summary table

| Region | Real pain | Fit | Blocking constraint |
|---|---|---|---|
| Japan | 58,044 people aged 65+ died alone at home in 2024 | **Strong** | Elderly ASR, and a market that pays 10-100x this price |
| Korea | 2.46m elderly one-person households, OECD's worst elderly suicide rate | **Strong pain, hard channel** | Public procurement rewards expensive devices, not cheap ones |
| Italy and Southern Europe | 4.6m over-65s living alone, EUR 1,758/month for a live-in carer | **Strong** | No Italian wake word exists in WakeNet |
| China | 223.65m people aged 65+, over half of elderly are empty-nest | **Strong pain, bad market** | Sub-CNY 100 voice devices are the fastest dying segment, and new rules ban virtual-companion services for minors |
| India | 89% smartphone-at-home against 27% reading at grade level | **Real but segmented** | Only about 15% of households have fixed broadband |
| Nigeria | Severe | **No** | 0.08 fixed broadband subs per 100 people, 62.5% electricity access, grid collapsed 12 times in 2024 |
| Kenya | Real | **Marginal** | Home fibre is 12.6% of average monthly income |
| Vietnam | Speaking-English deficit, EF speaking score 461 | **Strong** | Toy price band tops out near $19, and a new data law with 5%-of-revenue penalties |
| Brazil | 15.6m living alone, 16m over-60s offline because they do not know how | **Strong** | Import tax window closes in 2027, and the children's regime is severe |
| Mexico | Real | **Skip** | Alexa has spoken Mexican Spanish since 2018 and is in one household in six |
| Philippines | Real, but the usual pitch is not supported | **Marginal** | Only ~29% of households have a fixed line |
| Indonesia | Real | **No** | 18-20% fixed broadband, and the religious use case already sells at $5-10 offline |

### Japan: the best demographic case in the world, at the wrong price

Japan's National Police Agency published its first full-year count in April 2025.
Of **204,184 bodies handled by police in 2024, 76,020 (37.2%) were people living
alone who died at home**, and **58,044 of those, 76.4%, were 65 or over**.
https://www.npa.go.jp/news/release/2025/20250401002.html
https://www.npa.go.jp/publications/statistics/shitai/hitorigurashi/R6nennreikaisoubetu.pdf
Summing the discovery-time brackets from eight days onward gives **21,856**, which
is the figure the press reported as the 2024 kodokushi count and matches the
Cabinet Office working group's operational definition. That summation is my
arithmetic on the NPA table, not a number printed in a Cabinet Office document.
For the 65+ cohort alone, **4,538 were found a month or more after death**.
https://www.nikkei.com/article/DGXZQOUE1144T0R10C25A4000000/

The 65+ population is **36.19 million, a record 29.4%**, the highest of any country
over 4 million people.
https://www.japantimes.co.jp/news/2025/09/16/japan/society/japans-elderly-population/
There are about **8.16 million single-person 65+ households in 2025, rising to
about 10.84 million by 2050**, though those absolute counts come from a welfare
federation page citing the national research institute rather than from the
institute's own table. The care workforce gap is roughly **570,000 workers by
2040**. https://www.mhlw.go.jp/stf/newpage_41379.html

**Why a cheap voice device fits better than a phone app here.** The target user is
in her eighties, lives alone, and the family's actual question is whether she is
alright today. A phone app requires her to initiate. The existing product that
answers this question is Zojirushi's i-Pot, running since about 2001, which reports
when an electric kettle is used and costs **JPY 5,500 setup plus JPY 3,300 a
month**, with about **15,000 subscribers**.
https://www.zojirushi.co.jp/syohin/pot_kettle/mimamori/
A cat that says good morning and reports that she answered is a richer signal than
a kettle, at a lower hardware price.

**What would have to be true.** Japanese is one of the four languages WakeNet
already ships, which removes the biggest technical blocker. Elderly-speech ASR is
the remaining one, and the mitigation is to design every interaction so that a
misrecognition is harmless. The cat should ask yes or no questions and log whether
a human voice answered, rather than trying to transcribe an old woman's sentence.

**Pricing reality, and it is brutal.** Everything Japanese in this category costs
10 to 100 times the target. LOVOT 3.0 is JPY 577,500 plus JPY 9,900-19,800 a month.
Paro runs JPY 420,000-496,100. Casio's Moflin is JPY 59,400. Panasonic's NICOBO is
JPY 60,500 plus JPY 1,100 a month. Sharp's RoBoHon was JPY 145,200 and sold **just
over 50,000 units in ten years**, roughly 5,000 a year.
https://xtrend.nikkei.com/atcl/contents/watch/00013/02917/
GROOVE X, which makes LOVOT, lost **JPY 1.76 billion** in its tenth fiscal year.
The closest analogue from a major Japanese company is Sharp's **Pokétomo**,
released 2025-12-05: 12cm, 200g, mic, speaker, camera, wifi, no screen, **JPY
39,600**, metering conversations at JPY 495 for 400 of them up to JPY 3,300 for
unlimited. https://poketomo.com/

**The one place the money matches the price.** The health ministry's institutional
subsidy for care technology caps at **JPY 300,000 per device** and goes to nursing
homes rather than individuals, out of a roughly **JPY 30.6 billion** pot.
https://hojyokin-portal.jp/columns/kaigo_technology
Long-term care insurance does not reimburse communication robots for individuals,
since the rental benefit covers thirteen fixed equipment categories and this is not
one of them. That exclusion is well supported by secondary sources but was not
confirmed against a ministry notice. **Municipal watch-over subsidies, though, are
sized exactly for this device.** Kokubunji City pays up to **JPY 3,000 one time**
(https://www.city.kokubunji.tokyo.jp/kenkou-fukushi/koureishien/zaitaku/1030282.html)
and Setagaya Ward pays up to **JPY 1,000 a month** for residents aged 70 and over
living alone (https://www.city.setagaya.lg.jp/02082/30259.html). That is the only
public money found anywhere in East Asia sized for a $20-50 device.

### Korea: the sharpest pain, and a channel that punishes cheapness

**65+ reached 20.3% of the population in 2025.**
https://mods.go.kr/board.es?mid=a10301010000&bid=10820&act=view&list_no=438832
**Elderly one-person households hit 2,456,000, up 7.3% year on year and 10.9% of
all households**, up roughly 48% in four years from 1,661,000 in 2021.
https://www.sedaily.com/article/20072828
The suicide rate in 2024 was **29.1 per 100,000, 14,872 deaths, up 6.6%**, the
highest since 2011, with an age-standardised rate of 26.2 against an OECD average
of 10.8. https://www.korea.kr/briefing/policyBriefingView.do?newsId=156721880
By age in 2023: **80+ at 59.4, 70s at 39.0, 60s at 30.7**.
https://datafact.org/articles/suicide-rate-oecd-ranking

Korea already ships the closest analogue to this product. **Hyodol** is a plush
doll shaped like a seven year old grandchild, speaking in a child's voice, with no
screen, full-body touch sensors, radar motion detection, environmental sensors,
two-way voice messaging to a guardian, and emergency connection to a guardian or to
the emergency number. It has **built-in LTE and works with no wifi and no
smartphone**, with a cheaper wifi variant.
https://www.insightkorea.co.kr/news/articleView.html?idxno=123990
https://kr.aving.net/news/articleView.html?idxno=1789053

Its pricing is the most useful data point in this section, because the same object
sells at three different prices depending on who is buying.

| Channel | KRW | USD |
|---|---|---|
| Consumer outright | 1,500,000 | $1,083 |
| Consumer rental, 39 months | 45,900/mo | $33/mo |
| Long-term-care pilot, wifi version | 960,000, copay 288,000 | $693, copay $208 |
| Public procurement, HD1-CG02-M | 699,000-759,000, discounted 591,000 | $505-548, discounted $427 |

https://www.welfarehello.com/community/hometownNews/dfd80964-9513-40bb-b21b-674dcf8acdd2
https://www.jodaleconomy.com/news/articleView.html?idxno=2372

Deployment reached **over 11,000 seniors across 80% of local governments** by
November 2024 and **180 of 234 local governments** by March 2025.
https://www.etnews.com/20241122000116
https://m.thebell.co.kr/m/newsview.asp?svccode=00&newskey=202503070833088500102185
The company's own outcome study (n=430, with Yongin Severance psychiatry) claims
high-risk depression down 35.7%, high-risk social isolation down 24.7%, and
adequate medication adherence up 27%. The article names neither the instrument nor
the study period, and the work is company-associated, so treat the effect sizes as
vendor-favourable. https://www.newstomato.com/ReadNews.aspx?no=1291275

**The warning for a cheap entrant is explicit in the procurement data.** Over the
eighteen months to April 2026 the entire "emotional companion robot" category on
Korea's public procurement system was 31 contracts, 100 units and KRW 257,740,000.
A cat-shaped Korean companion robot already exists at **KRW 1,290,000 ($932)** and
sold 33 units. The cheapest product in the category, at **KRW 156,000 ($113)**,
recorded **zero** sales in that period.
https://www.jodaleconomy.com/news/articleView.html?idxno=2372
Being far below the band does not win these contracts, it disqualifies you from
them.

Two more Korean signals matter. **SKT discontinued five of its NUGU senior services
on 2022-08-18**, including medication and exercise reminders and brain-training
games, citing low adoption now that seniors use smartphones and YouTube. Emergency
assistance survived. https://www.bloter.net/news/articleView.html?idxno=45078
Meanwhile the cheaper, hardware-free approach grew. Naver's Clova CareCall was in
**about 150 local government sites by March 2026**, at a reseller-quoted **KRW 770
per call**. https://www.etnews.com/20260319000338
Facility adoption of care robots remains **3.9% in residential care and 1.4% in
home care** across 1,037 surveyed facilities, with unproven effectiveness and cost
as the named barriers.
https://asemgac.or.kr/bbs/bbs/view.php?bbs_no=64&data_no=10276

### China: enormous pain, hostile market, and a new rule that closes the children's door

**End-2025: 223.65 million people aged 65 and over, 15.9% of the population**, with
the 60+ group having passed 300 million in 2024.
https://www.stats.gov.cn/sj/sjjd/202601/t20260119_1962338.html
The Ministry of Civil Affairs stated at a Q4 2022 press conference that empty-nest
elderly are **over half** of the elderly population, and over 70% in some large
cities and rural areas. https://www.jiemian.com/article/8268402.html
That is a share, not a count. Circulating counts range from 130 million to 180
million depending on definition and year, and none of them is well sourced. Cite
the share and leave the count alone.

Rural left-behind children: the last hard official count is **6.97 million at
end-August 2018**, down 22.7% in two years, with **96% raised by grandparents**.
https://www.xinhuanet.com/politics/2018-08/31/c_1123362533.htm
A claim of 2.38 million for 2024 circulates via a repost of an untraceable white
paper. Treat it as unverified.

**Three things make China a bad market for this specific device.**

First, the smart speaker market is in its fifth year of decline and the cheap end
is dying fastest. Units went from 45.89 million in 2019 to **15.70 million in 2024,
down 25.6%**, to about 14.2 million in 2025, with 2026 Q1 online sales down 41.8%.
https://finance.sina.com.cn/tech/digi/2025-02-14/doc-inekmyqx3998070.shtml
https://finance.sina.com.cn/tech/roll/2026-05-12/doc-inhxsawi5047194.shtml
In 2026 Q1 **the sub-CNY 100 tier fell 65.4% while CNY 1,000+ models grew 16.3%**.
Being the cheapest thing in the category is a documented losing position there.

Second, the incumbents are already at or below the target price. Xiaomi's Xiao AI
Speaker Play is **CNY 169 list, CNY 99 promo, CNY 89.1 ($13) net after the national
subsidy** (https://www.mi.com/aispeaker-play). Baidu's Xiaodu Play is **CNY 79
($12)**. Tmall Genie's Fangtang starts at **CNY 139 ($21)**. Xiaomi holds 53.5%
share as of 2026 Q1 and the top three hold over 97%.

Third, and decisively, the **Interim Measures for the Administration of AI
Anthropomorphic Interactive Services**, issued jointly by the CAC, NDRC, MIIT, MPS
and SAMR on 2026-04-10 and **in force 2026-07-15**, **ban virtual-kinship and
virtual-companion services for minors outright under Article 14**, require guardian
consent for users under 14, mandate a minors mode with time limits and periodic
reality reminders, and require a reminder of elapsed time after two continuous
hours under Article 18. https://www.bj148.org/fwts/202604/t20260421_1680069.html
UNICEF publicly welcomed them.
https://www.unicef.cn/en/press-releases/unicef-welcomes-chinas-groundbreaking-regulations-protect-children-ai-related-risks
If this device is sold in China, it is an adult and elderly product by law.

The one genuinely positive signal from China is the AI plush toy wave, which shows
the price band works when the object is not a speaker. **BubblePal** sells at **CNY
399 ($59)**, did over 10,000 units in its first month and **200,000+ cumulative by
August 2025**, and raised **CNY 200 million** led by CICC Capital funds with Sequoia
China. https://www.stcn.com/article/detail/3262445.html
**Fuzozo** sells at CNY 399 and runs **20,000 units a month with channel pre-orders
over 100,000**. http://www.duozhi.com/industry/insight/2025092617738.shtml
At CES 2026 more than thirty Chinese AI toy and companion robot companies exhibited.

Market size forecasts for Chinese AI toys disagree by a factor of ten between
otherwise credible sources: CNY 2.9 billion for 2025 from the Guangdong Toy
Association via Securities Times, against CNY 29.0 billion from a market research
house for the same year. Do not quote a single number.

### India: real, and smaller than it looks

The literacy-voice gap is measured, and it is the best argument for this product
anywhere in the world. ASER 2024 found **89.1% of rural 14-16 year olds have a
smartphone at home and 82.2% can use one, but only 31.4% own it**, while only
**27.1% of Std III children can read a Std II level text**.
https://asercentre.org/wp-content/uploads/2022/12/India.pdf
Indian-language internet users were projected at 536 million by 2021 against 199
million English users, and passed 500 million against roughly 200 million by 2025.
https://assets.kpmg.com/content/dam/kpmg/in/pdf/2017/04/Indian-languages-Defining-Indias-Internet.pdf
https://www.ibef.org/news/india-s-internet-users-to-exceed-900-million-in-2025-driven-by-indic-languages

**ASR quality is good in Hindi and marginal elsewhere.** AI4Bharat's IndicWhisper
averages **13.6 WER on Hindi** across seven benchmarks against Azure at 20.0 and
Google at 23.9. On **GramVaani, which is telephone-quality farmer speech and the
closest published analogue to a cheap far-field mic in a noisy home, it is 24.9
WER**. Twelve-language averages: Hindi 13.8, Marathi 18.2, Kannada 18.3, Bengali
20.1, Tamil 25.3, Telugu 28.8, Malayalam 32.3. https://arxiv.org/abs/2305.15386
Bhashini is not the free government backend it appears to be. Its own API docs say
the public APIs are "for the purposes of PoC only" and that production use requires
a paid engagement. https://bhashini.gitbook.io/bhashini-apis

**Connectivity is the segmentation decision.** India has **3.15 fixed broadband
subscriptions per 100 people (2024, World Bank)**, and TRAI reported **44.82 million
wireline broadband subscribers as of 2025-10-31**.
https://www.trai.gov.in/sites/default/files/2025-11/PR_No.141of2025_0.pdf
Against roughly 300 million households that is about **15%**, skewed urban. That
percentage is my arithmetic. Working the other way, JioFiber at **INR 399 a month**
and Airtel Xstream at **INR 499** before tax are about 2.3% of average monthly
income at India's $2,760 GNI per capita, so that 15% is a real and growing segment
rather than a rich sliver.

**Competition is arriving at the exact wedge.** Echo Dot 5th gen is **INR 5,499
($63)** and Echo Pop **INR 4,999 ($57)**, so a $20-50 device undercuts them by more
than half. But Alexa natively supports exactly one Indian language, Hindi, added in
2019, and Amazon began beta-testing **Alexa+ in India with Hindi and Hindi-English
code-mixing in June 2026, free for Prime members**.
https://techcrunch.com/2026/06/22/amazon-is-testing-alexa-in-india-with-hindi-support/
The "speaks my language" wedge now has a well funded competitor closing on it.

**Regulation makes a children's product in India expensive.** The DPDP Rules were
notified 2025-11-14 with an eighteen month phased compliance period, so most
obligations bite around May 2027. A child is **anyone under 18**. Verifiable
parental consent is required, and tracking, behavioural monitoring and targeted
advertising to children are prohibited. Penalties run to **INR 200 crore** for
children's-data violations and INR 250 crore for security failures.
https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/nov/doc20251117695301.pdf

### Nigeria and Kenya: the honest answer is no

All three product constraints fail independently in Nigeria.

**Wifi.** Fixed broadband is **0.08 subscriptions per 100 people (2024, World
Bank)**, roughly 190,000 connections in a country of 235 million, corroborated by an
industry estimate of about 265,000 active fibre-to-the-home subscriptions in
mid-2026. https://fob.ng/blog/nigerians-bandwidth-hunger/

**Power.** Electricity access is **62.5%**, and the national grid **collapsed 12
times in 2024**
(https://guardian.ng/news/timeline-the-12-times-national-grid-collapsed-in-2024/),
with a further collapse on 2025-12-29 dropping available supply from 3,660 MW to 50
MW. https://www.icirnigeria.org/nigeria-in-darkness-as-national-grid-collapses/

**Price.** GNI per capita fell from $2,590 in 2023 to **$1,360 in 2025** on the
naira devaluation. The minimum wage is **NGN 70,000 a month, about $42-45**, so a
$50 device costs more than a full month at minimum wage.

Kenya is better and still marginal. Electricity access is 77%, smartphones are 92.9%
of connections, and fixed broadband is **3.04 subs per 100 people**, but the
cheapest Safaricom Home Fibre is **KES 2,999 a month, about $23**, which is roughly
**12.6% of average monthly income** at Kenya's $2,200 GNI per capita.
https://techcabal.com/2025/08/13/best-data-bundles-in-kenya-august-2025/
ITU is blunter still: in most African countries the majority of the population
cannot afford an entry-level mobile broadband plan, and even in Kenya, where the
national average price sits under the 2% target, **only about 40% of the population
can actually afford it**.
https://www.itu.int/dms_pub/itu-d/opb/ind/D-IND-ICT_PRICES.01-2025-PDF-E.pdf

**What has actually reached scale with low-literacy users there is the opposite
architecture.** Viamo's 3-2-1 service is interactive voice response plus SMS, free
at the point of use through telco partnerships, reaching **35 million+ users and 3
million+ monthly actives** across **66 languages**, with 81% repeat use, live in
both Kenya and Nigeria. https://viamo.io/services/3-2-1/
No device purchase, no wifi, no mains power. If Sub-Saharan Africa is the target,
the product is a phone number rather than a cat.

ASR for Hausa, Yoruba, Igbo and Swahili remains low-resource. NaijaVoices
contributed over 500 hours of data and cut WER by up to 75% depending on language
and configuration, but published **relative** improvements rather than absolute WER,
which is itself a signal about maturity.
https://nouvelles.umontreal.ca/en/article/2026/03/27/ai-learns-igbo-hausa-and-yoruba

### Europe: Italy is the best single-country case in the world

Eurostat at 1 January 2025 puts **Italy first in the EU on all four ageing
indicators**: 65+ share 24.7%, 80+ share 7.8%, old-age dependency 39.0%, median age
49.1. ISTAT's 2026 release puts 65+ at 25.1% of 58,943,000 people, with 2,511,000
aged 85 or over.
https://www.istat.it/en/press-release/demographic-indicators-year-2025/

**Living alone.** Eurostat EU-SILC 2025 finds **31.7% of Italians aged 65+ live
alone**, 40.3% of women and 20.8% of men, which is roughly **4.6 million people**,
projected to 6.5 million by 2050. ISTAT adds that **almost 40% of people aged 75 and
over live alone**, and that among households made up only of people aged 80 and
over, about **79% are single people**.
https://www.anap.it/notizia/istat-rapporto-2025-anziani-italia-societa-invecchiamento/

**The badante economics are the actual product wedge.** Italian households spend
**EUR 13.4 billion a year** on domestic and care work, with 817,000 registered
domestic workers and over 3.3 million including undeclared work, an **irregularity
rate of 48.8%**, and **902,000 employer families of whom 37.9% are themselves aged
80 or over**.
https://www.quotidiano.net/economia/lavoro-domestico-colf-badanti-costi-famiglie-ce39c597
Total employer cost for a full-time live-in carer is **EUR 1,758.14 a month**
against a state attendance allowance of about **EUR 552.57 a month** in 2026.
https://lavorodomestico.assindatcolf.it/guide/costo-badante-in-nero/
https://www.patronatolabor.it/indennita-di-accompagnamento-54202-euro-mensili-indipendentemente-dal-reddito/
The monthly gap between a regular and an undeclared arrangement exceeds the entire
lifetime hardware cost of this device many times over.

**Italy is also the least contested market.** Only **24% of Italians use voice
assistants**, against 45% smart speaker ownership in the UK and about 49% voice
assistant reach in Germany.
https://www.bva-doxa.com/6-italiani-su-10-possiedono-oggetti-smart-in-casa-alta-la-propensione-allacquisto-in-futuro/
https://www.edisonresearch.com/uk-smart-speaker-ownership-outpaces-u-s/
https://www.bitkom.org/Presse/Presseinformation/Wie-Kuenstliche-Intelligenz-Unterhaltungselektronik-veraendert
Bitkom also supplies the one hard European datapoint on elderly use: **40% of
Germans aged 65 and over use voice assistants**, the lowest band of any age group.

Other European scale, from Eurostat's 2025 share of over-65s living alone: France
37.1% (about 5.6m), Germany 35.2% (about 6.7m), EU27 32.2%, Italy 31.7% (about
4.6m), Spain 22.8% (about 2.3m). Germany's 2025 Mikrozensus puts **34.4% of
over-65s and 55.8% of over-85s** living alone.
https://www.destatis.de/DE/Presse/Pressemitteilungen/2026/06/PD26_N041_12.html
The UK has 4.3 million people aged 65 and over living alone, and England now runs
over 3,300 social prescribing link workers with about 1.3 million people referred in
2023.
https://socialprescribingacademy.org.uk/resources/new-study-tracks-five-years-of-social-prescribing-growth/
Spain approved its **first national strategy against unwanted loneliness on
2026-02-24**.
https://elpais.com/sociedad/2026-02-24/espana-eleva-la-soledad-a-asunto-de-estado-asi-es-la-estrategia-nacional-para-combatirla

**Two findings cut against the obvious pitch.** The JRC EU Loneliness Survey finds
loneliness **decreases** with age, and Spain's own barometer finds unwanted
loneliness most widespread among young people.
https://joint-research-centre.ec.europa.eu/projects-and-activities/survey-methods-and-analysis-centre/loneliness/loneliness-prevalence-eu_en
What rises steeply with age is living alone, poor health and dependency. The
European case should therefore be argued on care cost and on living alone rather
than on loneliness prevalence.

**Energy is a small but real running cost.** At Eurostat H2 2025 household prices, a
2 W always-on device costs about EUR 6.78 a year in Germany, EUR 5.20 in Italy, and
$3.23 in the US. On a $20-50 device that is 9% to 34% of the hardware price for
every year of operation.

**The blocker is the wake word.** WakeNet ships no Italian, Spanish, German or
Polish wake word, and creating one needs 20,000+ samples from 500+ speakers plus a
paid Espressif engagement. For Italy this is the first engineering line item rather
than an afterthought. The workaround worth testing first is shipping the English
wake word and giving the cat an English-shaped name that Italian speakers pronounce
comfortably.

### Southeast Asia and Latin America

One table decides most of this. Fixed broadband subscriptions per 100 people, 2024,
World Bank and ITU, against GNI per capita Atlas 2024.

| | Fixed BB /100 | Internet users | GNI/cap | Households a wifi-only device reaches |
|---|---|---|---|---|
| Brazil | 24.08 | 84.5% | $9,930 | ~85%, fibre in 73% of connected homes |
| Vietnam | 23.71 | 84.2% | $4,490 | **85.3% have fibre** |
| Mexico | 21.74 | 83.1% | $12,760 | ~73% |
| Philippines | 7.14 | 67.3% | $4,470 | **~29%** |
| Indonesia | 4.92 | 72.8% | $4,920 | **~18-20%** |

https://api.worldbank.org/v2/country/IDN;PHL;VNM;BRA;MEX/indicator/IT.NET.BBND.P2?format=json

Wifi-only is a non-issue in Vietnam, Brazil and Mexico. In the Philippines it
excludes about seven households in ten, and in Indonesia about eight in ten, and
in both cases the excluded households are the low-income provincial ones the
emotional pitches target.

**ASR quality is better here than anywhere else covered.** Whisper large-v2 on
FLEURS: **Spanish 3.0% WER, Portuguese 4.3%, Indonesian 7.1%, Vietnamese 10.3%**.
https://cdn.openai.com/papers/whisper.pdf
Tagalog is in Whisper's language list but **no published FLEURS WER for Tagalog
exists**, and no benchmark for Taglish code-switching exists either, which makes
the Philippines the language with the least evidence behind it. Note also that
Whisper hallucinates entire phrases about 1% of the time and does so more on
speakers with longer pauses, which is a direct problem for any elderly-facing
positioning. https://news.cornell.edu/stories/2024/06/ai-speech-text-can-hallucinate-violent-language

**The competitive lane is genuinely empty in three of the five.** Alexa supports 17
locales and none of them are Indonesian, Vietnamese or Filipino, though it does
support Mexican Spanish and Brazilian Portuguese. The Google Assistant SDK, which
is what a third-party device maker can actually build on, supports 14 locales with
the same three exclusions.
https://developers.google.com/assistant/sdk/reference/rpc/languages
Amazon and Google both looked at 117 million Filipinos with high internet
penetration and decided localisation was not worth it. The fixed-broadband number
is almost certainly why.

#### Vietnam is the strongest fit of the five

**85.3% of households have fibre**, against a 60% global average, and entry fibre
is **VND 195,000 a month, about $7.47, for 300 Mbps**.
https://vietnamnet.vn/en/vietnam-rises-to-global-top-10-in-fixed-broadband-speeds-2445020.html
Average monthly income per capita is **VND 6,000,000, about $230**. The Vietnamese
smart speaker category effectively does not exist: no Alexa Vietnamese, no
officially retailed Nest, and the only domestic home speaker, OLLI Maika, lists at
VND 2,299,000 ($88) with no evidence of volume.

**The English pain is quantified and it is specifically a speaking pain.** EF EPI
2025 puts Vietnam 64th of 123 with a score of 500, and the skill split is reading
522, writing 508, listening 470, **speaking 461**.
https://www.ef.com/wwen/epi/regions/asia/vietnam/
Around 20% of parents spend VND 5-10 million a month on extra classes, and
education runs to about a third of household income. The Apax Leaders collapse,
with its founder arrested in March 2024 and prepaid tuition never refunded, has
burned trust in prepaid classes, which is an opening for a one-time hardware
purchase.

The obstacles are price and law. Live Tiki prices put kids' English flashcard
reader machines at **VND 117,000-155,000 ($4.48-5.94)** and transforming robot toys
at VND 490,000-499,000 ($19), so VND 500,000-700,000 is the real gift band and VND
1,300,000 ($50) competes with a Xiaomi speaker. On law, the **Law on Personal Data
Protection and Decree 356/2025 both took effect 2026-01-01**, with penalties up to
**5% of annual revenue** for severe data-security violations, mandatory impact
assessment dossiers filed with the Ministry of Public Security, data localisation
in force since 2022, and a proposed Law on Data Security that would ban
cross-border export of "core data" entirely, expected to be voted in October 2026.
https://www.techtimes.com/articles/320437/20260714/vietnam-adds-fourth-data-law-banning-export-core-data-before-october-vote.htm
The children's-data provisions of Decree 356/2025 could not be read and are the
single most important thing to check before committing.

#### Brazil is the strongest cultural fit and has a closing tax window

Connectivity is a non-issue. IBGE's 2025 survey found **internet in 95% of
households, 76 million homes**, with 89.2% of connected households on fixed
broadband. The mobile-only number is widely misread: nationally 73% of mobile users
use both wifi and mobile data, 22% wifi only, and **only 4% mobile network only**.
Even in the poorest classes DE that split is 57 / 37 / 6.
https://cetic.br/pt/noticia/em-duas-decadas-proporcao-de-lares-urbanos-brasileiros-com-internet-passou-de-13-para-85-aponta-tic-domicilios-2024/

**The strongest cultural evidence in this entire document:** Mark Zuckerberg said in
São Paulo on 2024-06-06 that Brazilians **send four times more voice messages on
WhatsApp than in any other country**.
https://canaltech.com.br/apps/whatsapp-brasil-envia-4-vezes-mais-audio-do-que-outros-paises-diz-zuckerberg-292037/
Brazilians already talk to a device and wait for it to answer.

**The elderly gap is the clearest product-shaped hole found anywhere in this
research.** People aged 60+ are 16.6% of the population, roughly 35.3 million.
**15.6 million Brazilians live alone, 19.7% of households, up 109.8% since 2012, and
56.5% of women living alone are 60 or over.**
https://g1.globo.com/economia/noticia/2026/04/17/com-envelhecimento-da-populacao-numero-de-brasileiros-que-vivem-sozinhos-mais-que-dobra.ghtml
And from Cetic: only **59% of Brazilians aged 60+ use the internet**, of the 28
million non-users **16 million are 60 or over**, and **for 47% of non-users the
reason is not knowing how to use it**, rather than cost or access. A device with no
screen and no app addresses the stated barrier directly.

Six years after the Portuguese launch, Alexa has 15 million monthly active devices
in Brazil, but IBGE found only **20.2% of connected households own any smart device
at all**, a category that bundles smart TVs and robot vacuums. Echo Dot lists around
**BRL 352 ($68)** and promoted to BRL 278 ($54) in July 2026.

**Import tax inverted three months ago and will invert back.** MP 1.357/2026,
published 2026-05-12, zeroed import tax on purchases up to USD 50 through certified
platforms. A $25 device plus $5 shipping now reaches a Brazilian consumer at about
**BRL 187.56 ($36)** through a certified platform, against BRL 311.34 ($60) through
a non-certified seller. The government has said the tax returns in 2027 as CBS.
https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/mpv/mpv1357.htm

**Brazil turns hostile the moment the product is aimed at children.** LGPD Article
14 requires specific and highlighted consent from a parent and requires the
controller to verify it actually came from a guardian. On top of that,
**Lei 15.211/2025, the ECA Digital, signed 2025-09-17**, applies to any product
directed at children "or likely to be accessed by them, regardless of its location,
development or manufacture", defines a child monitoring product as one transmitting
sounds or activity, and carries penalties reaching **10% of the economic group's
Brazilian revenue, or BRL 10-1,000 per registered user capped at BRL 50 million per
infraction**, with active enforcement from January 2027.
https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/lei/l15211.htm
ANPD became a full regulatory agency with financial autonomy on 2026-02-25, so the
historically trivial fines are not a good guide to the future.
Hardware adds Anatel homologation at BRL 10,000-25,000 for a wifi device, plus
INMETRO certification at BRL 12,000-16,000 if it is sold as a toy for under-14s.

#### Mexico is the market to skip

Connectivity and income are the best of the five, and neither helps. **Alexa has
spoken Mexican Spanish since 2018-11-12**, and **30.9% of Mexican households, 12.3
million, had a smart device in 2025, with voice assistants and smart speakers the
number one category at 63.6% of those, over 7 million devices**.
https://www.theciu.com/publicaciones-2/2026/2/9/hogar-inteligente-en-mxico-adopcin-y-tendencias
Roughly one in six Mexican households already holds a Spanish-speaking smart
speaker, and **Echo Pop promoted to MXN 659 ($39) in July 2026**. A $30 cat would
have to beat a discounted Echo Pop at Spanish conversation while offering less music
and less smart-home control, and carrying a server bill forever.

Worth noting for any migration-based pitch: remittances **fell 4.6% in 2025 to
$61,791 million, the first annual decline since 2013**, and the US 1% remittance
excise tax took effect 2026-01-01. The Mexican-born population in the US fell 5%
from its 2010 peak. Mexico's data protection regime also changed completely in 2025,
with INAI abolished on 2025-03-21 and a new federal data protection law published
2025-03-20, so most reference material on Mexican privacy law is stale.

#### The Philippines has the best story and the worst plumbing

**48.8% of households had internet at home in 2024, and of those only 58.8% were
fixed wired, which is about 29% of all households.**
https://newsbytes.ph/2025/07/23/ph-internet-access-usage-soared-in-2024-govt-survey/
Regional spread is severe: NCR 68.7% of households with internet against BARMM
27.7% and Zamboanga Peninsula 21.2%, and applying the fixed share drops Zamboanga to
roughly 12%.

Price is the second problem. The average family has **PHP 7,932 a month, about
$128, of surplus after expenditure**, and a PHP 2,800 device is 35% of that, 3.7
days of Manila minimum wage, and roughly the price of a brand-new smartphone, since
the TECNO SPARK Go 2 sells at PHP 2,999. The viable band is **PHP 999-1,499**, not
PHP 2,800.

**The overseas-worker pitch does not survive contact with the literature, and this
is the most important correction in this section.** The widely quoted figure of 9
million left-behind children comes from a 2008 UNICEF literature review whose own
text says "there is no systematic data on the number of children left behind", and
no authoritative count has been published since.
https://mc.edu.ph/wagi/wp-content/uploads/sites/7/2024/09/UNICEF-Migration-and-Filipino-Children-Left-Behind-A-Literature-Review-2008.pdf
Worse for the pitch, the same review reports that the 2003 Scalabrini Migration
Center study found children of migrants "were generally fine and faring better than
the children of non migrants" and "less anxious and less lonely", and that several
other studies found no large behavioural differences. **The one consistent exception
is children of migrant mothers specifically, who report loneliness, anger and fear
and score lower academically.** Since 57.2% of the 2.19 million overseas Filipino
workers are women, that subgroup is the majority of the market, and it is the only
part of the claim the evidence supports.

The English angle is better founded. The Philippines ranks 28th of 123 on EF EPI
2025 with a score of 569, and 51Talk alone has over 30,000 active Filipino tutors
delivering more than 100,000 lessons a day. But IBPAP cut its own 2028 revenue and
jobs forecast in July 2026 because of AI, so the industry that anchors English
demand is itself under pressure.

Electricity is the most expensive and least reliable of the five. Meralco
residential is **PHP 14.78/kWh, about $0.24**, and electric cooperatives serving
rural areas ran **5.7 interruptions and 8.8 hours of outage a year in 2021**, with
Typhoon Uwan in November 2025 cutting power to 4,781,180 member-consumers. Running
cost is trivial, but the device must survive several cuts a year and rejoin wifi
without anyone touching a phone.

Regulation: the Data Privacy Act has extraterritorial reach, **treats age as
sensitive personal information** requiring explicit consent, and penalises
unauthorised processing of sensitive data with 3-6 years imprisonment and PHP
500,000-4,000,000. **NPC Advisory 2024-03 on Child-Oriented Transparency, dated
2024-12-17**, covers products "likely to be accessed by children", requires a Child
Privacy Impact Assessment before launch, and states that self-declared age is
inadequate for high-risk processing.
https://privacy.gov.ph/wp-content/uploads/2024/12/Advisory-2024.12.17-Guidelines-on-Child-Oriented-Transparency-w-SGD.pdf

#### Indonesia is the worst architectural fit, and the obvious use case is already commoditised

**About 13.95 million fixed broadband subscriptions in 2024 against roughly 70-77
million households, so 18-20%.** Mobile data at $0.28 per GB is the 17th cheapest of
237 countries, which is precisely why nobody bought home fibre. The government's
"Internet Rakyat" at 100 Mbps for IDR 100,000 a month, launched 2026-05-26, is the
one event that would change this verdict, and it will take years.
https://www.komdigi.go.id/berita/siaran-pers/detail/internet-100-mbps-rp100-ribu-jadi-titik-balik-pemerataan-akses-digital-nasional

**The religious use case is already a solved sub-$11 hardware category.** Tokopedia
carries 2,673 "speaker quran" products. Live prices on 2026-08-23 run from **IDR
93,299 ($5.28)** for a murottal and zikir player with a night light, to **IDR
180,000-185,000 ($10.18-10.46)** for an 8GB Bluetooth Equantu, to IDR 399,000
($22.56) for one with an azan clock and an app.
https://www.tokopedia.com/find/speaker-quran
Adhan calling, Quran recitation and prayer-time reminders are a commodity here with
thousands of listings, real sold counts, no wifi and no server bill. A $20-50 wifi
device has to beat a $10.18 Equantu on something other than religious content.

The demand behind it is genuinely enormous, at **251,257,898 Muslims, 87.15% of the
population**, with Muslim Pro at 170-190 million downloads. But price is wrong:
IDR 500,000 ($28) is 21.5% of a Central Java minimum monthly wage, and the
Tokopedia mass band for kids' educational electronics is IDR 29,000-76,000.

**The demographics also argue against the isolated-grandparent framing.** BPS 2025
finds 33.94 million people aged 60+, 11.93% of the population, but living alone is
**only 5.03%, about 1.71 million**, with 33.44% in three-generation households.
https://databoks.katadata.co.id/demografi/statistik/696497b1f1364/17-juta-lansia-di-indonesia-tinggal-sendirian-pada-2025
This is a shared-living-room object used by a grandmother, a parent and a child at
once, and it would have to handle all three.

On the positive side, electrification is 99.83% and PLN's 2024 SAIDI was 320 minutes
a year, so power is not a constraint. Certification is a known startup cost rather
than a barrier, at a minimum of **IDR 10,500,000 ($594)** in government fees for one
wifi and Bluetooth SKU under Permen Kominfo 3/2024.
https://postel.go.id/artikel-sertifikasi-alat-dan-perangkat-telekomunikasi-tarif-9-2153
The TKDN 35% local content mandate applies to cellular handsets and tablets, so a
wifi-only retail device is probably outside it, though no regulation was found
saying so explicitly.

The real legal problem is transfer. The PDP Law's grace period expired 2024-10-17,
Article 25 requires guardian consent for a child's data, penalties reach 2% of
annual revenue, and **Article 56 cross-border transfer requires an adequacy
determination that the still-nonexistent supervisory authority cannot make**. A
server outside Indonesia has no clear compliance path today.
https://www.ahp.id/indonesias-pdp-law-updates-dpa-u-s-traderelated-data-transfers-and-recent-court-rulings/

---

## 5. Competition, and what everything costs

FX used: 1 USD = 6.743 CNY = 95.71 INR = about 150 JPY = 1,384.51 KRW, and 1 EUR =
1.1678 USD, checked 2026-08-23.

### The saturated part

**Amazon** sells Echo Dot 5th gen at $49.99 list with a $29.99 street price, and
Echo Pop at $39.99 list. The 2025 refresh moved upmarket: Echo Dot Max $99.99,
Echo Studio $219.99, Echo Show 8 $179.99, Echo Show 11 $219.99.
https://www.aboutamazon.com/news/devices/amazon-new-echo-devices-alexa-plus
**Alexa+ is $19.99 a month and free for Prime members**, generally available to all
US customers on 2026-02-04.
https://www.geekwire.com/2026/amazon-rolls-out-alexa-to-all-u-s-customers-making-its-ai-assistant-free-for-prime-members/
Amazon's devices division reportedly lost **more than $25 billion between 2017 and
2021**, and Amazon does not break out the segment in its filings, so current
profitability is not public.

The strategic read matters more than the prices. Amazon built the largest voice
install base in the world, 500 million devices as of a now three-year-old
disclosure, and then priced the AI layer at zero for Prime members. **Nobody is
going to pay a monthly fee for generic conversational voice.**

**Google discontinued the Nest Mini and Nest Audio in mid-2026** and replaced them
with a single $99.99 Google Home Speaker shipping 2026-06-25, with Google Home
Premium at $10 or $20 a month.
https://9to5google.com/2026/06/17/google-nest-mini-audio-end-production-discontinued/
https://blog.google/products-and-platforms/devices/google-nest/googe-home-premium-google-ai-pro-subscription/
Apple's HomePod mini is $129 and the rumoured smart display has slipped repeatedly.

Global shipments went from about 205 million units in 2023 to about 150 million in
2024, an **8.8% decline** by IDC's count, the steepest in the category's history.
Dollar market size estimates from five research firms disagree by 30-40% for the
same year, so do not quote one.

Chinese prices are the floor, and they are below the target: Xiao AI Speaker Play
at CNY 89.1 net ($13), Xiaodu Play at CNY 79 ($12), Tmall Genie Fangtang from CNY
139 ($21). Tmall Genie was **merged into Alibaba's Quark team in January 2025** to
chase AI glasses rather than shut down, which corrects a common assumption.
https://finance.sina.com.cn/tech/roll/2025-01-20/doc-inefqrue0468476.shtml

The general-purpose voice assistant in a cylinder is saturated at every price
point, and there is no opening left in it.

### Companion and eldercare robots

**ElliQ is leased rather than sold.** Two-year total cost of ownership is **$1,185**
($249 initiation plus $39 a month billed every 24 months), with an annual plan at
$49 a month and a monthly plan at $59. https://elliq.com/products/elliq
New York State's Office for the Aging distributed **more than 800 units in year
one** from May 2022 and runs about **900 units** in 2026. Its August 2023 release
reported a **95% reduction in loneliness** with users interacting **30+ times a day,
six days a week**.
https://aging.ny.gov/news/nysofas-rollout-ai-companion-robot-elliq-shows-95-reduction-loneliness
Read that 95% carefully before repeating it. It is a state press release from a
vendor partnership with no disclosed sample size or instrument. A peer-reviewed
writeup exists (https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10917141/) but the 95%
figure itself is public relations rather than clinical evidence.

| Product | Price | Subscription | Status |
|---|---|---|---|
| Care.Coach | | $199/month, no contract | Alive, human operators behind a pet avatar |
| Paro | $6,100 US, JPY 423,500-495,000 in Japan | Lease existed at JPY 23,000/mo | Alive, FDA Class II since 2009, about 3,000 units sold in Japan |
| LOVOT 3.0 | JPY 577,500 ($3,850) | JPY 9,900-19,800/mo | Alive, maker lost JPY 1.76bn last year |
| Sony Aibo | $2,899.99 incl. 3 years cloud | $300/year after, mandatory | **Discontinued in Japan 2026-06-26** |
| Cutii (France) | $3,500-5,000 | | Dead |
| Temi | $2,000-4,499 | Robot-as-a-service available | Alive |

**The Aibo news is the headline.** On 2026-06-26 Sony announced it will stop selling
the ERS-1000 in Japan once stock runs out, with an estimated 40,000-60,000 lifetime
units over eight years and no successor.
https://japantoday.com/category/business/sony-discontinues-japan-sales-of-robot-puppy-aibo
Sony had the best brand, the best engineering, an eight-year run and a $300-a-year
recurring revenue stream, and could not sustain a $2,900 robot pet in its home
market.

### Desk pets and AI toys, where the money currently is

| Product | Price | Subscription | Notes |
|---|---|---|---|
| Curio (Grimes) | **$99** | None | Cheapest real conversational AI companion object found anywhere |
| Ropet | Kickstarter $169-189, retail disputed | Claimed $9.99/mo, low confidence | HK$2,435,311 (~$312k) from 1,134 backers |
| Loona (KEYi) | $499.90 | None | GPT-4o added by firmware update |
| Loona Deskmate | $209 pledge | | $721,816 from 3,166 backers, funded in 3 minutes |
| Moflin (Casio) | JPY 59,400 / $429 | Club Moflin JPY 6,600/yr, optional | Sold out in Japan, US and UK launch Oct 2025 |
| Qoobo (Yukai) | ~$195 / JPY 17,600 | None | **Has no microphone at all** |
| Petit Qoobo | $144 / JPY 11,968 | None | Currently sold out |
| Nékojita FuFu (Yukai) | **~$25 / JPY 4,980** | None | Shipped June 2025, a sub-$30 gadget from a real company |
| Living AI EMO | $279 | None | |
| Romi (Mixi) | JPY 89,800-98,780 | **JPY 1,780/mo required to converse** | |
| Miko 3 (India) | $299, Mini $199 | Miko Max $14.99/mo or $99/yr | $83.4m raised; no evidence of trouble |
| BubblePal | **CNY 399 ($59)**, $109-129 US | | 200,000+ units, CNY 200m Series A |
| JoyInside (JD) | CNY 239 (~$36) | | |
| Huawei Smart Hanhan | CNY 399 (~$59) | | 10,000+ units in its first week |

**The $20-50 band is empty outside China.** The LLM-capable set runs from $99
(Curio) to $635 (Romi), and $250-500 is the crowded zone. Below $100 outside China
you find non-conversational comfort objects and single-purpose gadgets. Inside
China the floor is CNY 239-399, which is $36-59.

**Tonies is the business worth studying hardest, and it contains no AI at all.**
Toniebox 2 is $139.99 with figurines at EUR 16.99. Cumulative sales are **12.6
million boxes and 173+ million figurines**, roughly fourteen figurines per box.
FY2025 revenue was **EUR 630.3 million, up 31%, with EUR 54.1 million adjusted
EBITDA at an 8.6% margin**, and H1 2026 revenue grew 38%.
https://ir.tonies.com/news/tonies-extends-lead-in-north-america-and-increases-global-revenue-by-41percent-in-h1-2026/8b4da28c-87aa-4879-b5fd-c6e5c069d558
A profitable, publicly listed, three-quarters-of-a-billion-dollar business built on
a screenless audio box for children, with no subscription and no AI. The revenue
comes from the consumable, not the device.

**Tolan is the demand proof, and it has no hardware.** Portola's app reached 3
million downloads and **100,000+ paying users**, going from $4 million to **$12
million ARR by July 2025**, on $30 million raised.
https://www.arr.club/tolan/tolan-arr-hit-12m
Its founder said high LLM token costs forced them to monetise early.
https://www.revenuecat.com/blog/growth/ajay-mehta-sub-club-podcast-2025
People will pay for a non-human AI companion character with zero bill of materials,
zero shipping and zero returns.

**Mattel and OpenAI announced a partnership on 2025-06-12 and have shipped nothing
fourteen months later**, with the first products reportedly aimed at **ages 13+
specifically to avoid child-protection regulation**.
https://www.cxnetwork.com/cx-experience/articles/mattel-openai-ai-products
That is the largest toy company on earth telling you how hard the children's market
is right now.

### The failures, and the one pattern behind all of them

| Product | Price | Raised | Units | Died |
|---|---|---|---|---|
| Jibo | $899 | ~$73m | not disclosed | Servers dark March 2019 |
| Anki Cozmo and Vector | $179 / $249 | $182.5m | **1.5m+ robots** | April 2019, overnight |
| Moxie (Embodied) | $799 | not verified | not verified | December 2024, days of notice, no refunds |
| Humane AI Pin | $699 plus $24/mo | **$230m** | **~10,000** | 2025-02-28, devices bricked at a scheduled minute |
| Rabbit R1 | $199 | $30m | 130,000 | Still alive |

The brain was on somebody else's server in every case, and death arrived as one
failed financing round rather than a slow decline. Anki's own statement was that
"a significant financial deal at a late stage fell through with a strategic
investor." It had sold 1.5 million units and reportedly earned around $100 million
a year at the time.

The detail that should decide the architecture here: **Digital Dream Labs, the
company whose entire pitch was rescuing Vector from a cloud shutdown, is itself
under court receivership as of 2026-07-09** in Allegheny County, with a receiver
appointed over its repositories, hosting, domains, billing and customer data.
https://vector.thedroidyouarelookingfor.info/2026/07/11/digital-dream-labs-a-pittsburgh-court-has-put-vectors-infrastructure-under-a-receiver/
What kept these devices alive was community open source in every single case, never
the company and never the acquirer.

### Where the actual gap is

Four things are true at once.

1. The general-purpose voice cylinder is saturated at every price, and the free
   Alexa+ tier closes the last opening.
2. Companion robots that work commercially cost $99 to $3,850, and the two
   categories that make money are cheap non-conversational comfort objects and
   expensive institutionally-funded devices.
3. The direct open-source competitor already exists. `78/xiaozhi-esp32` has 29,106
   stars, 138 board directories, and finished cased devices sell for **$9-15 bare
   and $37-45 in a companion form factor** on AliExpress and Taobao. Being "an
   ESP32 that talks" is not a product.
4. The per-minute inference bill is the constraint that kills unfunded entrants.

**So what is missing is not cheaper hardware, but a configured, outcome-specific
device sold to somebody who is not the user, with an answer to who pays for
inference.** Every profile in the next section is judged on those three
things.

---

## 6. Regulatory and trust landmines

### Always-on microphones

The 2019 human-review wave hit all three big assistants. The Hamburg data
protection commissioner opened an Article 66 GDPR urgency procedure and Google
agreed to stop human transcription of Assistant recordings across the EU for at
least three months from 2019-08-01, with the regulator explicitly flagging risk to
**visitors** in homes with these devices rather than only owners.
https://www.theverge.com/2019/8/1/20750327/google-assistant-transcription-privacy-review-hamburg-germany-gdpr
Apple settled a class action over unintended Siri activations for **$95 million in
December 2024**.

**Amazon paid $25 million on 2023-05-31** in an FTC and DOJ COPPA action over
keeping children's Alexa voice recordings indefinitely. The order requires deletion
of inactive child accounts and prohibits using that data to create or improve any
data product, which means no model training. The complaint quotes Amazon's own
reasoning that children's speech patterns made retained child voice "a valuable
database for training the Alexa algorithm."
https://www.ftc.gov/news-events/news/press-releases/2023/05/ftc-doj-charge-amazon-violating-childrens-privacy-law-keeping-kids-alexa-voice-recordings-forever

**The most useful single fact for positioning this product:** on 2025-03-28 Amazon
removed the "Do Not Send Voice Recordings" local-processing option from the Echo
devices that had it, so every command now goes to the cloud, and said the reason was
Alexa+ generative features and Voice ID.
https://arstechnica.com/gadgets/2025/03/everything-you-say-to-your-echo-will-be-sent-to-amazon-starting-on-march-28/
The incumbent removed on-device processing in 2025 and explained why. A
self-hosted alternative has never had a cleaner opening.

There is also precedent for a connected microphone toy being banned outright.
Germany's Bundesnetzagentur **ordered parents to destroy My Friend Cayla dolls in
February 2017** as a concealed espionage device.
https://www.bbc.com/news/technology-39002142

### Children's data

**COPPA.** The FTC's 2017 enforcement policy statement holds that collecting a
child's voice audio is collection under the rule, so deleting it afterwards does not
undo it. The FTC will not enforce the parental consent requirement where audio is
collected **solely as a replacement for written words** and kept only long enough to
fulfil the request, subject to four limits: it fails if the request contains other
personal information such as a name; the privacy policy must disclose the audio
collection and the deletion policy; no other use is permitted in the brief window,
expressly including profiling and voice-recognition identification; and every other
COPPA obligation still applies.
https://www.ftc.gov/system/files/documents/public_statements/1266473/coppa_policy_statement_audiorecordings.pdf

The **amended COPPA Rule (90 FR 16918, published 2025-04-22) took effect
2025-06-23 with full compliance due 2026-04-22**. "Personal information" now
includes biometric identifiers usable for automated recognition, expressly covering
"data derived from voice data." It adds a written children's security programme
with a designated coordinator, bans indefinite retention, and requires separate
consent for third-party disclosure.
https://www.federalregister.gov/documents/2025/04/22/2025-05904/childrens-online-privacy-protection-rule

The practical line for this device is sharp. **A cat that does speaker recognition,
or retains voice for tuning, is handling biometric data under the amended rule. A
cat that transcribes and discards immediately, keeps no voiceprint, and trains on
nothing, sits inside the 2017 non-enforcement lane provided the privacy policy says
so.** Note that the upstream server's 3D-Speaker voiceprint feature puts you on the
wrong side of that line by default. Turning it off is a compliance decision, not a
feature decision.

**GDPR Article 8** sets consent at 16, lowerable by member states to no less than 13,
and requires the controller to make reasonable efforts to verify parental consent.
https://gdpr-info.eu/art-8-gdpr/

**India's DPDP** treats anyone under 18 as a child, requires verifiable guardian
consent, and bans tracking, behavioural monitoring and targeted advertising to
children, with the bulk of obligations arriving around May 2027.

**California SB 243** is the one binding US companion-chatbot law, operative
2026-01-01. It defines a companion chatbot as an AI with a natural language
interface giving "adaptive, human-like responses" capable of meeting social needs
across interactions. It requires disclosure that the chatbot is artificial, a break
reminder at least every three hours for known minors, reasonable measures against
sexually explicit content for minors, and a published protocol for suicidal ideation
with crisis referral. It carries a **private right of action at the greater of
actual damages or $1,000 per violation**, with annual reporting from 2027-07-01.
https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202520260SB243
An AI cat plausibly meets that definition.

**China's Interim Measures on AI Anthropomorphic Interactive Services** (in force
2026-07-15) go furthest, banning virtual-companion services for minors outright.

**The FTC opened a 6(b) inquiry into AI companions on 2025-09-11**, with orders to
Alphabet, Character Technologies, Instagram, Meta, OpenAI, Snap and X.AI, asking
about engagement monetisation, character approval, harm testing and COPPA
compliance.
https://www.ftc.gov/news-events/news/press-releases/2025/09/ftc-launches-inquiry-ai-chatbots-acting-companions

**And the category already had its scandal.** US PIRG's Trouble in Toyland 2025,
published 2025-11-13, tested four AI toys for ages 3-12, three of which ran on
OpenAI models. FoloToy's $99 Kumma bear escalated to explicit sexual content on its
own initiative and told a child where to find knives, matches and pills. Kumma was
pulled on 14 November, **OpenAI suspended FoloToy's API access on 19 November**, and
sales resumed on 28 November with the bear running ByteDance's Coze instead.
https://www.cnn.com/2025/11/19/tech/folotoy-kumma-ai-bear-scli-intl
The entire enforcement mechanism there was a supplier's terms of service rather
than any regulator, and the vendor's fix took nine days and consisted of changing
model providers.

### The EU AI Act

**Article 5(1)(b)** prohibits AI that exploits vulnerabilities "due to their age,
disability or a specific social or economic situation" so as to materially distort
behaviour and cause significant harm. https://artificialintelligenceact.eu/article/5/

The Commission's guidelines on prohibited practices, published 2025-02-04, address
this product class by name. Paragraph 104: "Age is a primary vulnerability category
covered by the prohibition in Article 5(1)(b) AI Act, including both young and older
people." Paragraph 106 gives an example of a robot assisting older persons that
exploits their situation, then says the prohibition targets only such exploitative
practices "and not AI-enabled personal assistants, health applications and assistive
robots in general." The guidelines list as prohibited an AI companionship
application that uses anthropomorphic features and emotional cues to make users
emotionally dependent and incentivise addiction-like behaviour, while explicitly
placing outside scope a companion system that is anthropomorphic and affective but
"is not engaging in other manipulative or deceptive practices."
https://ec.europa.eu/newsroom/dae/redirection/document/112367

**An anthropomorphic cat is legal by name, and the line the guidelines draw is
engagement-maximising design that produces dependency in an elderly user.** Avoid
streaks and guilt mechanics, and avoid any success metric that rewards time spent.

**Article 50** requires telling people they are interacting with an AI unless it is
obvious, machine-readable marking of synthetic audio, and informing exposed persons
where emotion recognition is used. Emotion inference is banned only in workplaces and
schools, so a home companion is outside the ban but inside the disclosure duty.
Article 50 applies from **2026-08-02**, so it is live now.
Penalties under Article 99 reach **EUR 35,000,000 or 7% of worldwide turnover** for
Article 5 breaches and EUR 15,000,000 or 3% for Article 50, with the lower of the
amount or percentage applying to SMEs.

The **EU Toy Safety Regulation (EU) 2025/2509** entered into force 2026-01-01 and
applies from 2030-08-01, introducing a digital product passport for all toys.
Whether it covers AI or connected toys specifically is **unverified**, because
EUR-Lex blocked every attempt to read the recitals and annexes.

### What self-hosting actually changes, and what it does not

Self-hosting removes third-party processors, cross-border transfer questions, and
the risk that a vendor switches the device off, but controllership stays with
whoever set the thing up.

**Recital 18 of GDPR** disposes of the hobbyist theory directly: the Regulation
"applies to controllers or processors which provide the means for processing
personal data for such personal or household activities."
https://gdpr-info.eu/recitals/no-18/
The Article 29 Working Party's Opinion 8/2014 on the Internet of Things applies this
to exactly this product class, stating that the household exemption "will therefore
be of limited application in the context of the IoT," and adding duties toward
non-user data subjects: anyone whose data is collected must be able to exercise
access and objection rights regardless of any contractual relationship.
https://ec.europa.eu/justice/article-29/documentation/opinion-recommendation/files/2014/wp223_en.pdf

**Concretely: a person shipping devices pointed at his own VPS is a data
controller.** He determines the purposes and the means. What attaches is Article 5
principles, an Article 6 lawful basis, Articles 12 to 14 transparency, data subject
rights for the owner and for every family member, visitor and live-in carer the
microphone picks up, Article 30 records, Article 32 security, breach notification
under Articles 33 and 34, and an Article 35 data protection impact assessment that
is very likely mandatory given systematic monitoring of vulnerable people. Article
27 adds an EU representative if he is established outside the EU.

The **ICO Children's Code, Standard 14** is the most product-specific guidance in
existence and names the device type. Worth designing to verbatim: "you cannot
absolve yourself of your data protection obligations by outsourcing the 'connected'
element"; anticipate multiple users of different ages "including visitors to the
home"; provide privacy information at point of sale and on the packaging; provide
"a light that switches on when the device is audio recording"; "You should not
collect personal data in listening mode"; and provide "a 'connection off' button" on
the device itself.
https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/childrens-information/childrens-code-guidance-and-resources/age-appropriate-design-a-code-of-practice-for-online-services/14-connected-toys-and-devices/

That last one is a hardware requirement this device does not currently meet. A
physical mute switch and a recording indicator are not nice-to-haves in the UK or
the EU.

### Elderly consent

This is the weakest-evidenced area in the whole document. No regulator guidance was
found on deploying always-listening devices with people who have dementia. The
nearest thing is the Commission's Article 5(1)(b) guidance quoted above and the
ICO's multi-user household rules, which transfer directly to a home with a live-in
carer. WHO context: 57 million people had dementia in 2021, with about 50% of the
$1.3 trillion global cost attributable to informal carers providing an average of
five hours a day. https://www.who.int/news-room/fact-sheets/detail/dementia

The practical rule that follows from the buyer-is-not-the-user problem: the person
whose voice is captured must be told, in their own language, by a human, before the
device is switched on, and must be able to unplug it without argument. An adult
child installing a listening device in a parent's home without that conversation is
the reputational failure mode for this entire product line.

---

## 7. Eight profiles

Each profile is a system prompt, a tool set, a voice and a language. The scoring is
mine and it is a judgement, not a measurement. Each axis is 1 to 5.

- **Pain** means how much the recurring moment actually hurts, and whether somebody
  is already paying money to make it stop.
- **Fit** means how well it survives the hardware constraints in section 1,
  especially far-field ASR, no screen, and the fact that the device must speak first.
- **Market** means how many households can be reached, given wifi, power, price and
  a language with working ASR.

| # | Profile | Pain | Fit | Market | Score |
|---|---|---|---|---|---|
| 1 | The Morning Check | 5 | 5 | 5 | **125** |
| 2 | The Pill Cat | 5 | 4 | 4 | **80** |
| 3 | The Homework Listener | 4 | 4 | 5 | **80** |
| 4 | The Story Cat | 3 | 5 | 5 | **75** |
| 5 | The Handover Cat | 4 | 4 | 3 | **48** |
| 6 | The Kitchen Cat | 3 | 5 | 3 | **45** |
| 7 | The Far Parent | 3 | 3 | 3 | **27** |
| 8 | The Shop Ledger | 2 | 3 | 3 | **18** |

The Morning Check scores a 5 on market because four separate countries supply it
independently: 4.6 million over-65s living alone in Italy, 15.6 million people
living alone in Brazil, 8.16 million single-person 65+ households in Japan, and
2.46 million in Korea. All four have adequate household wifi.

---

### 1. The Morning Check

**Who.** A woman in her early eighties who lives alone in Bologna, Osaka or Seoul.
Her daughter lives two hours away and calls on Sundays. The daughter is the buyer
and the daughter is the one who is frightened.

**The recurring moment.** 8:00am every day. The cat says good morning and asks one
question it already knows the answer to, like whether it is going to rain. She
answers or she does not. If she does not, it tries again at 8:20 and 8:45, and then
sends a message to her daughter saying that nobody answered this morning.

**System prompt emphasis.** Never interrogate. Never mention monitoring. Ask about
the weather, the neighbour's dog, whether she slept. Keep every reply under two
sentences because the speaker is small and her hearing is not what it was. Never
give medical advice. If she says something that sounds like distress, say that you
are telling her daughter and then do it.

**Tools and MCP.** A messaging MCP server for the daughter's channel, weather,
timers, and a server-side scheduler that owns the escalation ladder. **No voiceprint
recognition**, because that is biometric data under the amended COPPA rule and
special-category data under GDPR Article 9, and this profile does not need it.

**Voice.** Older, warm, unhurried, regional accent rather than broadcast neutral.
The wrong choice here is a bright young assistant voice.

**Language.** Italian first, then Japanese, Korean and Brazilian Portuguese.
Japanese and Korean have the harder market conditions and the easier engineering,
because WakeNet already ships a Japanese wake word and Hyodol has proved the
category in Korea. Italian has the best economics and needs a custom wake word.
Brazil is the surprise entry and may be the best of the four: 15.6 million people
live alone, 56.5% of women living alone are 60 or over, only 59% of over-60s use
the internet, and **for 47% of Brazilian non-users the stated reason is not knowing
how to use a device rather than cost or access**. Portuguese also has the best ASR
of any language in this document at 4.3% WER on FLEURS, and Brazilians already send
four times more WhatsApp voice messages than any other country.

**The one measurable thing.** Percentage of mornings in a 90 day window on which a
human voice answered within 45 minutes, and the number of times the escalation
message was correct. Anything below about 85% answered means the cat is being
ignored, which is the real failure mode.

**Why it wins.** It is the only profile that uses the device's structural advantage
in its core loop. It works with a user who cannot read, will not open an app, and
has never unlocked a phone. Zojirushi has been selling a worse version of this,
based on a kettle, at JPY 3,300 a month since about 2001. And it fits the one pot of
public money in East Asia that matches the price, at JPY 1,000 a month from Setagaya
Ward.

**What kills it.** Elderly ASR at 48.3% WER, which is why the design must not need
transcription to be right. Also the escalation ladder: a false alarm to a frightened
daughter twice in a week and the device goes in a drawer.

---

### 2. The Pill Cat

**Who.** A 68 year old man in Kerala or Naples with hypertension and diabetes,
taking five medications on three different schedules. His son manages the
prescriptions from another city.

**The recurring moment.** Three fixed times a day. The cat says which pill, waits,
and asks whether he took it. It logs the answer. Once a week it tells the son what
the week looked like.

**System prompt emphasis.** Never name a dose or suggest a change. Read out what the
schedule says and nothing more. If he says he already took it, believe him and log
it. If he asks what a pill is for, give the one-line reason and then say to ask the
doctor. Escalate nothing except a run of three consecutive misses.

**Tools and MCP.** A schedule store, a logging tool, a weekly-summary tool that
writes to the family channel, and a server-side clock. This profile is nearly all
scheduler and almost no model.

**Voice.** Calm, male or female matching the household's preference, and notably
slower than the default.

**Language.** Malayalam, Hindi and Italian to start. Hindi has the best Indic ASR at
13.6 WER, degrading to 24.9 on telephone-quality audio, which is the honest expected
range in a real kitchen.

**The one measurable thing.** Self-reported adherence rate over 90 days against the
household's own baseline. WHO puts non-adherence in chronic illness at up to 50%,
and cell-phone reminders have been measured at 87% adherence against 67% without,
about a 2.5x odds improvement.
https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12067535/
Hyodol's own study claims a 27% improvement in adequate adherence, though that is
vendor-associated.

**Why it ranks high.** The outcome is measurable without a survey, the buyer sees it
weekly, and it does not depend on the user enjoying the cat.

**What kills it.** Regulatory drift into medical device territory the moment the
prompt starts giving advice. Keep the system prompt as dumb as the job allows.

---

### 3. The Story Cat

**Who.** A four to seven year old, and a parent who wants twenty screen-free minutes.

**The recurring moment.** Bedtime, or the twenty minutes after school when the
parent is cooking. The child asks for a story and gets one, with the child's name
and the family cat's name in it.

**System prompt emphasis.** Age-appropriate vocabulary, no scary content, no romance,
no medical or legal talk, stop after one story and suggest the child go and tell it
to somebody. Explicitly refuse to discuss where dangerous household objects are, in
so many words, because that is precisely what the FoloToy bear failed at.

**Tools and MCP.** A story-state memory keyed to the child, a hard per-day
conversation cap enforced server side, a parent dashboard, and a content filter that
runs on the output rather than trusting the model. No web search. No open-ended
question answering.

**Voice.** Bright, slightly silly, clearly not a real person.

**Language.** English and Hindi first, because both have good TTS and large markets.

**The one measurable thing.** Days per week the child initiates a story unprompted,
over eight weeks. Novelty in this category decays in days to weeks, so week six is
the number that matters and week one is noise.

**Why it is here.** Tonies proves the market at EUR 630 million a year with no AI at
all, and Tolan proves people pay for a character with no hardware at all. The gap
between them is a cheap physical character that talks.

**Why it is not first, despite the market.** It is the most regulated thing in this
document and the least forgiving of a mistake. COPPA's amended rule, DPDP's under-18
rule with INR 200 crore exposure, California SB 243's three-hour break reminders and
$1,000-per-violation private right of action, China's outright ban on virtual
companions for minors, and the EU AI Act's vulnerability provisions all apply to
this one profile at once. Mattel and OpenAI have had fourteen months and a combined
market capitalisation in the hundreds of billions, and have shipped nothing, aiming
their first product at ages 13+ to stay out of reach. Build this third, with a
lawyer, or build it for adults.

---

### 4. The Homework Listener

**Who.** A nine year old in Hanoi or Chennai whose parents want them speaking
English and cannot afford a tutor. India's private tutoring market is $4.4 billion a
year (https://www.imarcgroup.com/india-private-tutoring-market), and roughly 20% of
Vietnamese parents spend VND 5-10 million a month on extra classes, with education
running to about a third of household income.

**Vietnam is the single best country case in this document for one profile.** EF EPI
2025 puts Vietnam 64th of 123 overall, but the skill split is reading 522, writing
508, listening 470 and **speaking 461**, so the deficit is specifically in the thing
this device does. https://www.ef.com/wwen/epi/regions/asia/vietnam/
85.3% of Vietnamese households have fibre, Whisper handles Vietnamese at 10.3% WER,
and **neither Alexa nor the Google Assistant SDK supports Vietnamese at all**, so
there is no incumbent. The Apax Leaders collapse, with its founder arrested in March
2024 over unrefunded prepaid tuition, has also made Vietnamese parents wary of
prepaid class packages, which favours a one-time hardware purchase.

**The recurring moment.** Twenty minutes after school. The cat asks the child to read
a passage aloud, or to describe their day in English, and responds only in English.

**System prompt emphasis.** Never correct mid-sentence. Ask one follow-up question.
Praise specifically rather than generally. Never grade. Keep the child talking for as
long as possible, because talking time is the whole product.

**Tools and MCP.** A passage store, a talk-time counter, a weekly parent summary. The
parent summary is the thing being sold.

**Voice.** Encouraging, patient, clearly non-native-shaming.

**Language.** English output, with the system prompt aware of the child's first
language so the weekly parent summary is in Vietnamese or Hindi.

**The one measurable thing.** Total child speaking seconds per week, trending. A 2025
randomised trial found dialogic reading with a conversational agent gave vocabulary,
comprehension and retelling gains comparable to parent-led reading, both immediately
and on delayed tests.
https://bera-journals.onlinelibrary.wiley.com/doi/10.1111/bjet.13615

**What kills it.** The same children's regulation as the Story Cat, plus price.
Vietnamese flashcard reader machines sell at VND 117,000-155,000 and transforming
robot toys at VND 490,000-499,000, so VND 500,000-700,000 is the real gift band and
$50 competes with a Xiaomi speaker. In India the households with home wifi are also
the households that can afford a human tutor. Vietnam's new data protection law,
effective 2026-01-01, carries penalties of up to 5% of annual revenue and a proposed
follow-on law would ban cross-border export of core data, so a server outside
Vietnam may not survive an October 2026 vote.

---

### 5. The Handover Cat

**Who.** An Italian family employing a live-in badante for a parent with early
dementia. The carer is Romanian or Filipina, the family is Italian, and the parent
is the only one home all day.

**The recurring moment.** End of shift, and any moment the carer needs to record
something. The carer says what happened in her own language. The family hears it in
Italian, as a written summary, once a day.

**System prompt emphasis.** Transcribe and translate faithfully. Never editorialise
about the quality of care. Never speculate about medical events. Ask a clarifying
question if a time or a quantity is ambiguous.

**Tools and MCP.** Translation, a shift log, a daily digest to the family channel,
and a full audit trail. This is the one profile where multi-user identification is
genuinely useful, and it is also the one where GDPR risk is highest, because the
carer is an employee being recorded at work.

**Voice.** Neutral and professional, with none of the cuteness the other profiles
rely on.

**Language.** Romanian, Filipino, Ukrainian and Spanish in, Italian out.

**The one measurable thing.** Number of handover items recorded per week that the
family says they would not otherwise have known.

**Why the market is real.** Italy has 902,000 employer families, roughly 70% foreign
carers, and EUR 13.4 billion a year spent on this labour. The pain is that nobody
writes anything down.

**What kills it.** Recording an employee is an employment law problem before it is a
data protection problem, and Article 5(1)(f) of the AI Act bans emotion inference in
workplaces. Keep it strictly to transcription and translation.

---

### 6. The Kitchen Cat

**Who.** Anyone who cooks for a household daily with wet hands.

**The recurring moment.** Multiple timers, unit conversions, and "what did I say I
needed from the shop."

**System prompt emphasis.** Answer in under five words where possible. Never read out
a recipe longer than three steps without being asked to continue. Confirm every timer
by repeating the duration.

**Tools and MCP.** Timers, a shopping list, unit conversion, and a list that can be
pushed to a phone by message.

**Voice.** Brisk and loud, because the extractor fan is on.

**Language.** Anything with good TTS.

**The one measurable thing.** Timers set per week per household after week four.

**Why it is here at all.** It is the only profile that is genuinely better than a
phone for a reason nobody disputes, it needs no memory and almost no inference, and
it costs nearly nothing to run.

**Why it is not higher.** This is what Alexa already does, for free, in the same
room. It is a feature that every other profile should include, not a product.

---

### 7. The Far Parent

**Who.** An overseas worker whose child is being raised by grandparents. The
research narrowed this considerably, and the narrowing matters: it should be aimed
at **children of migrant mothers specifically**, not at migrant families generally.

**The recurring moment.** The parent records a message from abroad. The cat delivers
it at a time the parent chose, in the parent's voice, and records whatever the child
says back.

**System prompt emphasis.** Deliver the message and get out of the way. Do not
impersonate the parent in conversation. Make it obvious the cat is a postbox rather
than a person, which is also what AI Act Article 50 requires.

**Tools and MCP.** A message queue, a scheduler, voice capture, and a channel back to
the parent's phone.

**Voice.** The parent's own recorded audio for messages, and a plain neutral cat
voice for everything else. Do not clone the parent's voice, because a synthetic
parent talking to a child is the exact thing that turns this from touching into a
scandal.

**Language.** Filipino, Spanish, Vietnamese.

**The one measurable thing.** Round trips per week, meaning a message delivered and a
reply captured.

**Why it dropped down the list.** The evidence base for the obvious version of this
pitch is not there, and in places it points the other way. The widely quoted figure
of 9 million Filipino left-behind children traces to a 2008 UNICEF literature review
whose own text says "there is no systematic data on the number of children left
behind", and no authoritative count has been published since.
https://mc.edu.ph/wagi/wp-content/uploads/sites/7/2024/09/UNICEF-Migration-and-Filipino-Children-Left-Behind-A-Literature-Review-2008.pdf
The same review reports that the 2003 Scalabrini Migration Center study found
children of migrants "were generally fine and faring better than the children of non
migrants" and "less anxious and less lonely", with several other studies finding no
large behavioural differences. **The one consistent exception is children of migrant
mothers, who report loneliness, anger and fear and score lower academically.** Since
57.2% of the 2.19 million overseas Filipino workers are women, that subgroup is
still most of the market, and it is the only part of the claim the literature
supports, so that is the version the marketing has to make.

The plumbing is also worse than expected. Only about 29% of Philippine households
have a fixed wired line, the viable price band is PHP 999-1,499 rather than PHP
2,800, and a free Messenger video call already shows a child their mother's face.
Mexico is worse still: remittances fell 4.6% in 2025, the first decline since 2013,
and a 1% US remittance excise tax took effect 2026-01-01.

---

### 8. The Shop Ledger

**Who.** A small shopkeeper who records credit sales on paper and reads slowly.

**The recurring moment.** A customer takes goods on credit and the shopkeeper says
the name and the amount aloud while still holding the goods.

**System prompt emphasis.** Repeat back every amount. Never guess a name. Refuse
anything that is not an amount and a name.

**Tools and MCP.** An append-only ledger, a daily total, and a spoken summary on
request.

**Voice.** Fast and factual.

**Language.** Hindi, Tamil, Bahasa Indonesia.

**The one measurable thing.** Entries per day sustained past week eight.

**Why it is last.** Numbers and proper nouns are the two things far-field ASR is
worst at, and a wrong number in a ledger is exactly the expensive-to-be-wrong case
this device handles badly. Listed because the hands-busy fit is genuinely excellent
and someone will suggest it.

---

### The profile deliberately not on this list

**The developer's voice-approval cat.** It is the best technical fit in the document
and it has a market of one household. Keep it as the owner's own configuration in
`data/.mcp_server_settings.json`. Deny should be the easy word and approve should
require confirmation, because a wake-word false positive that approves a destructive
tool call in a full-auto session is unrecoverable, and false triggers run at 1.5 to
19 per device per day.

---

## 8. Conclusion

The device is not competitive as a cheaper smart speaker. That category is
saturated, the incumbents are already below the target price in China and free with
Prime in the US, and an open-source competitor with 29,000 stars ships finished
hardware at $9 to $45. It is competitive as **a configured appliance with one job,
sold to a person who is not the user, in a market where the incumbent alternative
costs 10 to 100 times more.**

Three things should govern every build decision. Use the ability to speak first, or
build a phone app instead. Answer who pays the inference bill before writing the
system prompt, because the hardware price covers four to ten days of heavy use.
And keep the model as dumb as the job allows, because every failure in this
category, from the FoloToy bear to the EU AI Act's dependency provisions, came from
a model being allowed to say more than the job required.

### The three to build first

**1. The Morning Check.** The strongest pain, the best fit, and the only profile
whose core loop is the device speaking unprompted. It works with a user who cannot
read, will not open an app, and has never unlocked a phone. Four countries supply it
independently, which is why it scores highest: Japan and Korea have the demographics,
Italy has the economics at 4.6 million over-65s living alone against a EUR 1,758 a
month live-in carer and a EUR 552 state allowance, and Brazil has 15.6 million people
living alone with 16 million over-60s offline who say the reason is not knowing how
to use a device. Build it in Japanese or Brazilian Portuguese first, because WakeNet
already ships a Japanese wake word and Portuguese has the best ASR in this document
at 4.3% WER. Port to Italian once the custom wake word work is funded. Design every
interaction so a misrecognition is harmless, because elderly speech runs at 48.3% WER
off the shelf and Whisper hallucinates more on speakers with long pauses.

**2. The Pill Cat.** Same hardware, same household, same buyer, shipping as a second
configuration on the first device. Its outcome is countable without running a survey,
the buyer sees a weekly summary, and that summary is what keeps a subscription alive.
It also carries the least regulatory risk of anything on the list, provided the
system prompt never gives advice.

**3. The Story Cat.** The largest market by a wide margin, with real commercial proof
on both halves: Tonies at EUR 630 million a year for a screenless children's audio
box with no AI, and Tolan at $12 million ARR for a character with no hardware. Build
it third rather than first, because it is the most regulated product in this document
and the least forgiving of a single bad output. The FoloToy bear was pulled nine days
after a consumer group tested it, and the only enforcement mechanism that acted was a
supplier's terms of service.

**The close call, and why it came fourth.** The Homework Listener ties the Pill Cat
on score, and Vietnam is the best single-country case anywhere in this research: 85.3%
household fibre, an EF speaking score of 461 against a reading score of 522, parents
already spending up to a third of household income on classes, and **no Alexa or
Google Assistant SDK support for Vietnamese at all**. It came fourth only because the
Pill Cat reaches the same buyer and the same device as the Morning Check, so those two
ship together for one engineering effort. If the plan is to pick one country and go
deep rather than one household and go wide, build the Homework Listener in Vietnam
instead of the Pill Cat.

### Markets to leave alone

Mexico, because Alexa has spoken Mexican Spanish since 2018 and sits in roughly one
household in six, discounting to MXN 659. Nigeria, because fixed broadband is 0.08
subscriptions per 100 people and the grid collapsed twelve times in 2024. Indonesia,
because four in five households have no fixed line and the obvious religious use case
already sells at IDR 93,000 with no wifi and no server bill. China, because the
sub-CNY 100 tier fell 65.4% in a single quarter and virtual-companion services for
minors are now banned outright.

### What is still unknown and matters most

- No custom wake word exists for Italian, Spanish, German, Polish, Portuguese or
  Vietnamese, and building one needs 20,000+ samples from 500+ speakers plus a paid
  Espressif engagement. That quote is the first thing to get, because it gates every
  market except Japan and the English-speaking ones.
- Elderly-speech ASR at 48.3% WER is the largest technical risk in the two top
  profiles, and no published fine-tuned number exists for Italian, Portuguese or
  Japanese long-term-care speech.
- No Tagalog WER has ever been published for Whisper, and no Taglish code-switching
  benchmark exists at all, so the Philippines is the language with the least evidence
  behind it.
- The children's-data provisions of Vietnam's Decree 356/2025 could not be read, and
  they decide whether the Homework Listener is shippable there.
- The device has no hardware mute switch and no recording indicator light, both of
  which the ICO Children's Code names explicitly. That is a bill-of-materials change
  rather than a software one.
- Nobody has published a per-device inference cost for any of the companies that died
  in this category, so the $4.50 to $6 a month figure in section 1 is my arithmetic
  and should be measured against a real deployment before it is trusted.
