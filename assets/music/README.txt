PitchPilot background music
===========================

Drop one or more royalty-free audio tracks into this folder to enable background
music. Supported: .mp3 .wav .m4a .aac .ogg .flac

How it works
------------
- Enable with ENABLE_BG_MUSIC=true in .env.
- One track is chosen at random per run, looped for the full video length, and
  automatically ducked under the narration (music dips while someone is speaking,
  rises in the gaps). BG_MUSIC_VOLUME sets the music level in the gaps.

Licensing — use CC0 / public-domain only
-----------------------------------------
Only add tracks you have the right to use. Prefer CC0 / public-domain so no
attribution is required and the video is safe to share commercially.

Suggested CC0 sources (corporate / uplifting):
  - Pixabay Music         — Pixabay Content License: royalty-free, no attribution.
  - FreePD.com            — CC0 / public domain (note: site closed in 2025).

Tracks currently bundled (origin + license):
  - jonasblakewood-corporate-background-corporate-background-music-524146.mp3
      Pixabay (pixabay.com/music) — Pixabay Content License, no attribution required.
  - kornevmusic-upbeat-happy-corporate-487426.mp3
      Pixabay (pixabay.com/music) — Pixabay Content License, no attribution required.
  - sigmamusicart-corporate-corporate-music-537730.mp3
      Pixabay (pixabay.com/music) — Pixabay Content License, no attribution required.
  - sigmamusicart-soft-inspiring-corporate-background-music-409687.mp3
      Pixabay (pixabay.com/music) — Pixabay Content License, no attribution required.

Note: the Pixabay Content License permits use in videos (incl. commercial) with no
attribution, but discourages redistributing the raw audio files on a standalone
basis. If this repo is public, consider whether to commit these files or keep them
local. Swap in true CC0 tracks if you need unrestricted redistribution.
