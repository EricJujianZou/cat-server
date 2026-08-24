# Voices, and what they cost

Three services do three jobs, and only two of them cost anything.

| Job | Service | Cost |
|---|---|---|
| Your voice into text | OpenAI `gpt-4o-mini-transcribe` | about $0.003 per minute |
| The replies | OpenAI `gpt-4o-mini` | per token |
| Text into speech | Microsoft Edge TTS | nothing, and no key |

Edge TTS is the free endpoint behind Edge's Read Aloud feature. It carries 324
voices across every language the browser supports.

## Where to actually hear them

The Azure voice gallery is the wrong place to browse. It lists Azure's paid
catalogue, which includes Dragon HD, Turbo and Multilingual v2 voices that Edge
TTS does not serve. Picking one there and putting it in a profile fails.

Two places that only show what works:

1. **Edge's own Read Aloud.** Open any page in Edge, right click, Read aloud,
   then Voice options. That picker is the same list this server can use.
2. **The dashboard's voice browser.** Filter by language, type your own sample
   text, press play. It builds its list from
   `docker exec cat-server edge-tts --list-voices`, so it cannot show a voice
   that does not work.

For the raw list without leaving the terminal:

```powershell
docker exec cat-server edge-tts --list-voices
```

## The one rule that catches everyone

The server wraps every profile's prompt in its own template, and that template
hardcodes an output language. So `voice` and `language` have to move together:

```yaml
TTS:
  EdgeTTS:
    voice: zh-CN-XiaoyiNeural
    language: Chinese
```

Set a Chinese voice and leave the language on English and the cat answers in
English in a Chinese accent. Set the language to Chinese and leave an English
voice and it reads Chinese text with English phonemes, which sounds like static
and is what sent us looking at the Opus encoder for a problem that was never
there.

## Bilingual, and why there is no clean answer

Edge has Multilingual voices that handle several languages in one voice. None of
them is Chinese-based. The set is German, French, Italian, Korean, Brazilian
Portuguese and four American English ones.

So the choice is between two compromises:

- A Chinese voice sounds native in Chinese and has a heavy accent in English.
- An American Multilingual voice is decent in both and native in neither.

`zh-CN-XiaoyiNeural` is the current pick. Its English is noticeably better than
`zh-CN-XiaoxiaoNeural`, which was the first candidate.

## Whether to pay for a better voice

Assume the cat speaks for about four minutes a day, which is 120 minutes a
month. Section 8 of the use case research puts the whole per-device budget at
$4.50 to $6 a month, so that is the number any TTS bill has to fit inside.

| Service | Roughly per minute | Per device per month | Share of the budget |
|---|---|---|---|
| Edge TTS | $0 | $0 | none |
| OpenAI `gpt-4o-mini-tts` | $0.015 | $1.80 | about a third |
| ElevenLabs Flash | $0.08 to $0.11 | $10 to $13 | twice the whole budget |
| ElevenLabs standard | $0.16 to $0.22 | $19 to $26 | four times the whole budget |

The ElevenLabs figures are derived from its published credit tiers rather than
read off a price-per-minute page, and they were worked out from memory rather
than fetched, so check them before making a decision that depends on the exact
number. The conclusion does not depend on the exact number. ElevenLabs alone
costs more per device than the research allows for transcription, the model and
speech synthesis combined.

That leaves one honest argument for paying, and it is not quality in general. It
is whether a specific profile fails without it. The Story Cat is the only
candidate, because a child notices a flat voice and an adult checking their
medication schedule does not.

Edge stays until a profile can show it is losing on voice quality specifically.
