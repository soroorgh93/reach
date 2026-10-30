# Reach for judges

The same brief, live, is at **`/judge`** on the running app.

## In one sentence

Reach builds an evidence-graded music-medicine session (sleep, calm, focus, mood, memory, sensory-safe for autistic children, a visual mode for people who can't hear) out of the music a person already loves, in their own culture. Qloo's taste graph chooses every artist, podcast, film, place and book. Without Qloo, Reach refuses to compose.

## Sixty seconds

1. Open **`/judge`** and press **Run a session**. You see every Qloo call the agents made (`agent.purpose`, status, live or cached, time), the picks, and the hash-chained ledger. Press **Verify the ledger** to check it on the server.
2. Open the app (**`/?app=1`**), add two or three artists you love and your city, and type *"I can't sleep"*. Your own artists come first, then Qloo's picks close to each of them, on a slowing tempo path.
3. Open the **After the music** tab: a place, a table and a book near your city from the same taste, in a 3D night map. Every card says which favourite it is close to.
4. Set hearing to *none* in **About me**: the council switches to the visual protocol (breathing light, vibration, films and shows from your taste with captions).

## Inside an assistant

Add `https://<the server>/mcp` to Claude or ChatGPT as a custom connector. Tools: `compose_session`, `after_the_music`, `explain_evidence`, `reach_vs_chatbot`. Each answer carries a link that opens the session in the app.

## How Qloo is used

| Qloo surface | What Reach does with it |
|---|---|
| `/search` | turns typed favourites into entity ids, on the server |
| artist insights + protocol genre tags (`filter.tags`, union; `filter.exclude.tags`) | the carrier: artists that fit the protocol's texture |
| artist insights + `signal.location.query` | the cultural pool: artists linked to the favourites in the favourites' own culture (place from MusicBrainz) |
| tag insights (`filter.tag.types`) | the texture of the person's taste → instrument palette, mood and tempo bias |
| demographics | the audience lens of the favourites |
| podcast insights | shows for the genres the person's artists sing |
| movie / tv_show insights + `filter.content_rating` | the visual carrier for people who can't hear, child-rated for children |
| place insights + `filter.location.query` + `urn:tag:category:place:*` | After the music: parks, libraries, museums and restaurants near the person |
| book insights | After the music: a book from the same taste |
| `feature.explainability` | every "close to Hayedeh" label |

Parameters are checked against an allow-list for each type before a request is built (the API ignores unknown parameters silently). Requests are spaced for the hackathon rate limit, retried on 429 and cached.

## From request to result (one real path, redacted)
1. The person types **Hayedeh** and taps **I can't sleep**. Reach's server calls Qloo `/search?query=Hayedeh&types=urn:entity:artist` and keeps the artist entity (not the albums or people with the same name).
2. The Clinician picks the **Sleep descent** protocol (evidence grade A: Cochrane 2022, music for insomnia). Its texture rule becomes Qloo tags: `filter.tags=urn:tag:genre:music:ambient,…acoustic,…classical,…piano` (union) and `filter.exclude.tags=…metal,…edm,…hip_hop,…punk`.
3. The Taste agent asks `/v2/insights` with `filter.type=urn:entity:artist`, `signal.interests.entities=<Hayedeh's id>` and those tags, plus a second call with `signal.location.query=Tehran` (where MusicBrainz says Hayedeh is from) for her own culture's pool.
4. Reach ranks Qloo's candidates on its own rules: release language and country (MusicBrainz), the language of the song titles, slots per favourite, diversity. A Turkish pop singer Qloo ranked high is set aside, and the reply says so.
5. The Composer writes the timeline (62 to 49 beats a minute, pulse 10 Hz down to 2 Hz, volume at most −14 dBFS), the Guardian checks the safety rules, and the Gate approves. Every step is SHA-256 chained; `/judge` shows the actual calls and verifies the chain.

Sent to Qloo in all of this: entity ids, tag ids, an age bucket, a city. Never the words "I can't sleep".

## Known limitations: what Reach does not establish
- A Qloo affinity describes the aggregate taste of people who love the same things. It is not a prediction about one person, and Reach never uses it to infer health, identity or traits.
- Reach is a wellbeing tool, not a medical device. The music-for-stress and music-for-sleep claims are grade A; brainwave entrainment (binaural or isochronic pulses, 40 Hz) is labelled experimental (grade C or D) in the app.
- Previews are 30 seconds (open catalogues). Full songs need a YouTube key and play only when YouTube allows the video on other sites; otherwise Reach falls back to the preview.
- Where an artist comes from relies on MusicBrainz; an artist missing there is never treated as "foreign", just unknown.
- Without a conversation model on the server, free speech is understood by rules in four languages (English, Spanish, Persian, Chinese). The interface is in fourteen; in the ten newest, the council's own sentences fall back to English unless a language model is on.
- The comparison with a chatbot uses one local model (llama 3.1 8B) on ten people; it shows the pattern, not a clinical result.

## Sent and never sent

Sent to Qloo: entity ids, genre and place-category tags, an age bucket (child or adult), a city.
Never sent: the person's words, face, voice, mood, the goal itself, or their name.

## Against a plain chatbot

`python scripts/bench.py` gives ten people from different cultures (and lively favourites who need sleep) to a generic playlist, a language model asked directly, and Reach, and measures culture match, songs that exist, calm picks for sleep, personal answers, and Qloo taste fit. Results: `data/bench_results.json`, shown on `/judge`.

## Where each criterion shows

* **Technological implementation**: the table above; `reach/qloo.py`, `reach/taste.py` (two-stage ranking: Qloo candidates, then culture, language, feedback, quotas per favourite, MMR diversity), `reach/after.py`; the live receipts on `/judge`.
* **Design**: a 3D start page that shows every capability as a world you can fly to, a frequency instrument with a 3D Chladni plate, the 3D film introduction, the 3D night map, push-to-talk with ducking, hand gestures, fourteen languages including right-to-left Persian and Arabic, installable on a phone.
* **Potential impact**: music lowers anxiety and pain (81 trials, 5,576 people with cancer, Cochrane 2021), but generic calm playlists get switched off. Safety rules for children, autism and hearing loss (`data/protocols.json`, the clinic chapter).
* **Quality of the idea**: taste as the carrier of a clinical protocol. The protocol decides the tempo path, pulse band and safety envelope; Qloo decides what music carries it.

## Run it

```
pip install -r requirements.txt
cp .env.example .env        # put QLOO_API_KEY in it
python -m uvicorn server.app:app --port 8000
python -m unittest discover -s tests
```

MIT licence (`LICENSE`).
