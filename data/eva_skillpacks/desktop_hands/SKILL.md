# Desktop Hands

Use this skill when Victor asks Eva to open an app, website, media, map, video, Spotify, YouTube, Brave, Cursor, Obsidian, or interact with the visible screen.

Operating pattern:

1. Prefer the dedicated local bridge first: browser, Spotify, Cursor, Obsidian, desktop control, screen vision.
2. If the app can be opened by command or known executable, open it directly.
3. If the task depends on the visible UI, read the screen and identify the target element before clicking.
4. For fragile UI actions, report confidence and stop before external sends/publication unless policy allows it.
5. If one route fails, use another safe route: desktop app -> web app -> search page -> clipboard prompt.

Examples:

- "ouvre YouTube" -> open Brave on YouTube.
- "ouvre une carte de Londres" -> show a real interactive map or open maps in Brave, not just text.
- "mets Spotify" -> open Spotify or Spotify Web and search the requested music.

Never claim that media is playing, a button was clicked, or a page is loaded unless the tool confirms it.
