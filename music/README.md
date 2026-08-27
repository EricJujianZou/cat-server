# music

Drop mp3 or wav files here and the cat can play them through its own speaker.

This folder is mounted read-only into the container at
`/opt/xiaozhi-esp32-server/music`, where the bundled `play_music` plugin looks
for its library. Subfolders are searched too, and the filename without the
extension is the name you ask for out loud, so name files the way you would say
them.

The plugin is on in the claude-voice profile, which is allowed because this
folder is no longer empty: two royalty-free Kevin MacLeod tracks live here as
proof the pipe works. Replace them with music you actually want. If the folder
ever goes back to empty, take `play_music` back out of the profile's functions
list, on the repo's standing rule that the model is never told it can do
something it will fail at. New files are picked up within five minutes, no
rebuild needed.

Audio files in this folder are gitignored. This README is the only thing
committed.
