# Devpost submission: copy each part into its field

## Project name
Reach: your own music, made into medicine

## Elevator pitch (Devpost allows 200 characters)
An agent that turns the music you already love into an evidence-graded session for sleep, calm, focus or memory, in your own culture, grounded in Qloo's taste graph. Without Qloo it refuses to play.

## Try it out (links)
- Live app: https://YOUR-RENDER-ADDRESS.onrender.com
- For judges (60-second brief with live receipts): https://YOUR-RENDER-ADDRESS.onrender.com/judge
- README as a page (pictures, the face film, how it works): https://YOUR-RENDER-ADDRESS.onrender.com/readme
- Code: https://github.com/soroorgh93/reach

## Built with
python, starlette, uvicorn, qloo, three.js, kling-ai, web-audio-api, mediapipe, face-api.js, musicbrainz, deezer, itunes, youtube, ollama, llama, model-context-protocol, docker, render

---

## About the project

### Inspiration
Music measurably lowers anxiety and pain. A Cochrane review of 81 trials with 5,576 people with cancer found it, and another Cochrane review found music improves sleep in insomnia. But in hospitals and sleep apps, everyone gets the same "calm playlist": Enya, Max Richter, rain. A Persian grandmother who loves Hayedeh, a Taiwanese student who loves Jay Chou, a dancer who loves David Guetta all get the same list, and it gets switched off. Music that is medicine only works if people keep listening, and people keep listening to music that is theirs.

Ask a chatbot instead and it invents. In our test, a language model asked for Persian sleep songs named eight; none of them could be found in the Deezer or iTunes catalogues.

Reach is the missing piece: the clinical protocol decides *how* the session runs, and the person's own cultural taste, through Qloo, decides *what music carries it*.

### Who it's for
Three of these are demo profiles you can open on `/judge`; the first takes ten seconds on the start page (*Start my session*, type Hayedeh, choose *Memory*).
- **A grandmother in memory care** who grew up with Hayedeh and Googoosh. Her own songs come first, then the singers Qloo links to them in her own culture; afterwards Reach offers the family one gentle next step, a Persian kitchen near her. Music-based therapy probably improves depressive symptoms in dementia (Cochrane 2025: 30 studies, 1,720 people, mostly in care homes). Reach's 40 Hz layer for memory is labelled experimental, never treatment.
- **Lena, 7, autistic and minimally verbal**, melting down after school because the lights and noise got to her. She loves *Thomas & Friends* and *Bluey*. The sensory-safe protocol keeps her favourites at the core with a steady pulse, no surprises and a lower volume cap (−20 dBFS), because sound sensitivity is common in autism.
- **Daniel, 34, deaf since birth**, awake at 1 a.m. for six months. Reach refuses him an auditory session and says why, then routes to the visual protocol: a breathing light at six breaths a minute, phone vibration on the beat, and films and shows Qloo picks from his taste (*Blade Runner 2049*, *Dune*), captioned.
- **Mateo, 24, who has Down syndrome** and speaks Spanish. He wants to focus before speech therapy. Bad Bunny and Shakira carry a focus session, and the whole conversation happens in Spanish.

The same agent serves all four, and a room of them together: one session chosen to be fair to everyone in it.

### Why Reach, and not a plan or a playlist
- **It plays the session, it doesn't just suggest one.** Reach composes and performs the session live in the browser, from the first tempo to the last fade. There is nothing for a carer to assemble.
- **It listens back.** Face, voice and one hand are read on the device; the mood dial moves, and every twenty seconds the session meets the person where they are. Two fingers play the next song, a thumbs-down changes it and is remembered.
- **One agent, eight needs.** Sleep, calm, focus, mood, memory, energy, sensory-safe sessions for autistic children, and a session without sound for people who can't hear.
- **Evidence you can check.** Every protocol shows its grade (A to D) and its sources; experimental parts say so. Every step is written to a SHA-256 hash chain that a care team can verify.
- **Every culture, measured, not listed.** No country table anywhere in the code: language and origin come from open data, so the same code serves Persian, Mandarin, Afrobeats, K-pop and Mexican listeners.

### What it does
- **You say what you love and what you need.** "I love Hayedeh and Googoosh, I can't sleep." You can type, speak, or tap a one-tap example on the start page. Pick one need, or two for a journey (calm, then sleep; energy, then focus): one session that meets you where you are and leads you to the second. Fourteen languages, with Persian and Arabic right to left.
- **A council of agents builds the session.** Listener, Taste (Qloo), Clinician, Composer, Guardian and Gate.
  - It opens with **your own artists**, then the ones **Qloo's taste graph links to them, in your own culture**. A Persian listener gets Ebi and Googoosh, not a Turkish pop singer Qloo happened to rank higher.
  - It runs on an **evidence-graded protocol**: a tempo that starts at your pace and slows, a gentle pulse in the right frequency band, and a safe volume. Every claim shows its grade (A to D) and source, and experimental parts are labelled experimental.
  - It explains every pick ("Ebi, close to Hayedeh") using Qloo's explainability.
- **It is safe by design.**
  - Child and autism limits on volume, pulse and tempo.
  - Hearing and tinnitus rules, and never while driving.
  - Lively favourites at bedtime? Reach plays calm instrumentals instead of Britney.
  - A Gate refuses when the evidence or Qloo is missing.
- **The start page is the whole idea in one 3D picture:** a listener in headphones, her brain lit, and eight worlds around her, one per capability. Click a world to fly to it, watch a short clip of the real app, and open that part.
- **A guided tour** (top right): four minutes, spoken in a natural voice and captioned, with a film of the real app reading one hand and a face. While it speaks, every other sound waits.
- **With others:** a row per person, a name and who they love. Each favourite is looked up in Qloo, and the session is chosen to be fair to everyone in the room (Bayes, minimax and least-favourable weighting, shown in the trace).
- **Frequencies you can play:** five bands, speakers or headphones, low or high pitch. Each band draws its own figure in sand on a 3D plate and states its evidence grade.
- **It adapts while it plays.**
  - Talk to it in your own words: "I said Hayedeh, why another singer?", "only Dariush", "softer", "no vocals".
  - Optional on-device camera mood reading and hand gestures (two fingers for next).
  - Push-to-talk that ducks the music so it hears you.
  - A 3D frequency plate shows each frequency drawing its own figure.
- **For people who can't hear:** a visual protocol with a breathing light, phone vibration on the beat, and captioned films and shows Qloo picks from your taste.
- **After the music:** one gentle next step near you, from the same taste. A park or garden after calm, a library after focus, the kitchen of the songs after a memory session (Persian restaurants for Hayedeh), and a book. It's shown on a 3D night map of your city. Never a bar.
- **Inside your assistant:** Reach is an MCP server, so Claude or ChatGPT can call `compose_session` mid-conversation and get the plan, the evidence and a link that plays it.
- **For care teams:** the full trace, the evidence registry with sources, the safety rules, and a hash-chained ledger you can verify (and tamper with, to watch it break).

### How it's Qloo-powered
Qloo isn't a lookup at the end; it's the carrier of the whole session. Reach uses eight Qloo surfaces:
1. **Entity search:** your favourites become Qloo ids, on the server.
2. **Artist insights with protocol genre filters:** artists that fit the session's texture (ambient, acoustic, classical for sleep; never metal or EDM).
3. **The location signal:** the cultural candidate pool, using where your own artists come from (from MusicBrainz).
4. **Tag insights:** the texture of your taste, which sets the instrument palette, mood and tempo bias.
5. **Demographics:** the audience lens.
6. **Podcast insights:** shows for the genres your artists sing.
7. **Movie and TV insights with content ratings:** the visual carrier for deaf users.
8. **Place and book insights with category filters:** After the music.

Explainability drives every "close to …" label.

Then Reach ranks Qloo's candidates in a second stage it owns:
- MusicBrainz language and country;
- a title-language model;
- slots shared out per favourite, so a Shakira + Aznavour fan gets both Latin and French;
- diversity (MMR);
- what you finished or skipped.

**Without Qloo, there is no session: Reach refuses.**

### With Qloo, and without
Reach shows the difference two ways, and both run live:
- **In the app** (Clinic chapter, *Without Qloo*): the generic list any model hands everyone for the same need, next to the carrier Qloo built for this person, both scored by Qloo affinity to *this* person, with the lift and how many generic picks don't appear in their top fifty.
- **On ten people**, below.

### Measured against a plain chatbot
`scripts/bench.py` gives the same ten people (Persian, Mandarin, Afrobeats, K-pop, Turkish, Bollywood, Mexican, techno, a Shakira + Aznavour mix, and lively favourites who need sleep) to three systems: a generic playlist, a language model (llama 3.1 8B) and Reach. It measures, on picks that aren't the person's own favourites:
- songs that really exist (checked in the Deezer and iTunes catalogues, in any spelling);
- picks from the person's own culture;
- calm picks when they need sleep;
- different answers for different people.

Results (live Qloo, 28 October 2026):

| | Reach | Plain chatbot | Generic playlist |
|---|---|---|---|
| Songs that really exist | **100%** | 60% | 100% |
| From the person's own culture | **92%** | 89% | 36% |
| Calm when they need sleep or calm | **96%** | 70% | 100% |
| Different people, different answers | **80%** | 91% | 0% |
| Qloo taste fit (favours Reach by construction) | 0.76 | 0.37 | 0 |

The chatbot invents four songs in ten. The generic playlist is real and calm but the same for everyone, from someone else's culture. Reach is the only system strong on all four. The same numbers are on `/judge`. The method is in the script, including the one measure that favours Reach by construction (Qloo affinity), which we show rather than hide.

### From request to result (one real path, redacted)
1. The person types **Hayedeh** and taps **I can't sleep**. Reach's server calls Qloo `/search?query=Hayedeh&types=urn:entity:artist` and keeps the artist entity (not the albums or people with the same name).
2. The Clinician picks the **Sleep descent** protocol (evidence grade A: Cochrane 2022, music for insomnia). Its texture rule becomes Qloo tags: `filter.tags=urn:tag:genre:music:ambient,…acoustic,…classical,…piano` (union) and `filter.exclude.tags=…metal,…edm,…hip_hop,…punk`.
3. The Taste agent asks `/v2/insights` with `filter.type=urn:entity:artist`, `signal.interests.entities=<Hayedeh's id>` and those tags, plus a second call with `signal.location.query=Tehran` (where MusicBrainz says Hayedeh is from) for her own culture's pool.
4. Reach ranks Qloo's candidates on its own rules: release language and country (MusicBrainz), the language of the song titles, slots per favourite, diversity. A Turkish pop singer Qloo ranked high is set aside, and the reply says so.
5. The Composer writes the timeline (62 to 49 beats a minute, pulse 10 Hz down to 2 Hz, volume at most −14 dBFS), the Guardian checks the safety rules, and the Gate approves. Every step is SHA-256 chained; `/judge` shows the actual calls and verifies the chain.

Sent to Qloo in all of this: entity ids, tag ids, an age bucket, a city. Never the words "I can't sleep".

### Known limitations: what Reach does not establish
- A Qloo affinity describes the aggregate taste of people who love the same things. It is not a prediction about one person, and Reach never uses it to infer health, identity or traits.
- Reach is a wellbeing tool, not a medical device. The music-for-stress and music-for-sleep claims are grade A; brainwave entrainment (binaural or isochronic pulses, 40 Hz) is labelled experimental (grade C or D) in the app.
- Previews are 30 seconds (open catalogues). Full songs need a YouTube key and play only when YouTube allows the video on other sites; otherwise Reach falls back to the preview.
- Where an artist comes from relies on MusicBrainz; an artist missing there is never treated as "foreign", just unknown.
- Without a conversation model on the server, free speech is understood by rules in four languages (English, Spanish, Persian, Chinese). The interface is in fourteen; in the ten newest, the council's own sentences fall back to English unless a language model is on.
- The comparison with a chatbot uses one local model (llama 3.1 8B) on ten people; it shows the pattern, not a clinical result.

### AI tools we used
- **Qloo** (the taste graph): every artist, podcast, film, place and book Reach suggests.
- **Kling AI**: the start-page portrait, the brain and neuron images in the story, and the cat-and-hand clip.
- **Claude** (Anthropic): help with code, design and writing.
- **Ollama with llama 3.1 8B** (optional, on the server): understanding free speech in a conversation; also the plain chatbot Reach is measured against.
- **face-api.js and MediaPipe** (in the browser, on the device): reading mood from the face and hand gestures, only when the person turns them on.
- The demo film's music (Bach, Prelude in C; Beethoven, Ode to Joy) is public domain, recorded for Reach with a General MIDI soundfont, not generated.

### How we built it
- **Server:** Python and Starlette, with a council of agents, a decision layer (Bayes, minimax, least-favourable prior), a composer that follows the ISO principle (start at the listener's state, then lead), and a SHA-256 hash-chained ledger.
- **Browser:** Web Audio synthesis and entrainment; three.js for the film, the frequency plate and the 3D night map; face-api.js and MediaPipe running on the device; a PWA you can install on a phone.
- **Conversation:** rules in four languages, an interface in fourteen, plus an optional local language model (Ollama), so words stay on the machine.
- **Open data:** MusicBrainz, Deezer and iTunes previews, Internet Archive soundscapes, and optional YouTube full songs.
- **Delivery:** one Docker container (text served gzipped; the first screen is under 1 MB), an MCP endpoint, and 54 tests run on every push.

### Challenges we ran into
- **Culture, not country labels.** Our first ranking put Turkish singers in a Persian listener's playlist because Qloo ranked them higher, and an early reply said "from Iran", which felt wrong to our test user. We replaced labels with measurement: the language of an artist's own song titles, where MusicBrainz says they're from, and slots shared per favourite, so every favourite gets its own picks.
- **Real songs only.** Persian and Chinese names are spelled many ways, and two different artists can share a name (there are two "Dariush" on Deezer). Reach now picks the artist listeners actually mean and plays that artist's own songs.
- **Safety vs. taste.** If you love techno and need sleep, your taste is the wrong medicine tonight. The Guardian switches to calm instrumentals and says why.

### Accomplishments that we're proud of
- It works for people most apps forget: a deaf user, a 7-year-old, a grandmother who speaks Persian.
- Every claim carries its evidence grade and source; experimental things are labelled experimental.
- Privacy by design: no account, no database, request logs off, face and voice read on the device, and nothing personal sent to Qloo. `/privacy` says where every piece goes.

### What we learned
Cultural intelligence isn't a nice extra for health; it's adherence. The same protocol works better when people want to keep listening, and only real taste data, not a model's guess, can tell you what that music is.

### The business
**Who pays:**
- **Memory-care homes and hospitals**, per bed per month. They get the care-team view, the evidence and the ledger for audit, and nothing personal is stored, so there is no patient database to secure. There are 57 million people living with dementia, with nearly 10 million new cases every year (WHO).
- **Music therapists**, who prepare a personal session in a minute and leave it with the patient between visits.
- **Sleep, wellness and assistant apps**, per session, through the API and the MCP server: any assistant can call `compose_session` and play the result.
- **People at home**: the core free, with full songs and sessions for a room of people by subscription.

**Why it scales:** one container, no account and no database; the main cost per session is its Qloo calls. The same agent serves every language and culture without new data, because culture is measured from open sources rather than written into tables.

### What's next
- Pilots with music therapists and memory-care homes.
- A caregiver mode for dementia reminiscence.
- Outcome tracking (sleep diaries, anxiety scales) to grade Reach's own sessions.
- Spoken replies in all fourteen languages without a language model.

---

## Before you submit
1. Replace the YOUR-RENDER-ADDRESS placeholders with your real Render address (the GitHub link is already filled in).
2. On GitHub, open the repo's **About** (the gear icon) and make sure the **MIT** licence shows. The rules require the licence to be visible there.
3. Images are ready in `docs/media/`: `cover_3x2.jpg` for the project thumbnail (Devpost crops to 3:2), `cover_16x9_4k.jpg` as the first gallery image, and `universe_4k.jpg` as a clean background. All three are rendered from the app's own 3D start page, so what judges see is what they get. Add 2–4 more screenshots: a session playing, After the music (3D map), Persian, and `/judge`.
4. `docs/media/reach_film_bach.mp4` (Bach, Prelude in C) and `reach_film_ode.mp4` (Beethoven, Ode to Joy) are the same 12-second fly-through of the start page with two soundtracks, both public-domain music recorded for Reach. Devpost's video field takes a YouTube or Vimeo link: upload it there (unlisted is fine) if you want a video, or skip it.
5. A longer demo video isn't required. Leave it out rather than rush one.
