# Validation record / 验证记录 / 検証記録

Date: **2026-11-19**. Tested on macOS / Apple Silicon, Python 3.14.2, Flask 3.1.3, requests 2.34.2, python-dotenv 1.2.4, installed Google Chrome through Playwright 1.65.2.

## Real installation and browser entry

A new `.venv` was created inside this project. Dependencies were installed from `requirements.txt`, private configuration was loaded through the documented `.env` mechanism, and the normal `python app.py` entry was started on `127.0.0.1:8791`.

The browser opened the real page and used New project → Create cues → Save draft → Generate this cue. No request payload was injected to bypass the product UI for the paid generation.

## One real RunningHub generation

- Region: `https://www.runninghub.cn`.
- Endpoint: `POST /openapi/v2/rhart-audio/text-to-audio/speech-02-hd`.
- Input: `Welcome to the gallery. Take a moment to notice the light.`
- Settings: `Wise_Woman`, speed `1`, volume `1`, pitch `0`, emotion `neutral`, `enable_base64_output=false`, `english_normalization=false`.
- **Exactly one live submission** was made for this test. Follow-up operations queried that task and downloaded its output.
- Observed states: `QUEUED` → `SUCCESS`; not every intermediate state must be observed by a poller.
- Saved file: MP3, **77,748 bytes**, **4.7 seconds** as measured by the browser audio element.
- The browser audio element reached `readyState=4`; playback advanced beyond one second. This verifies decoding and playback, not a subjective voice-quality score.
- Exported ZIP contained one numbered MP3, `script.md`, and `manifest.json`. The MP3 and parameter snapshot were read back from the ZIP and matched the test input.
- Refresh restored the same successful take and selected version without another submission.
- Public demonstration: [sample-narration.mp3](assets/sample-narration.mp3).

## Browser checks

| Check | Result |
|---|---|
| Desktop 1440 px | Real input/edit/generate/query/audio/export flow passed |
| Mobile 390 px | Layout inspected; document width remained 390 px, no horizontal overflow |
| Browser JavaScript errors | None observed |
| Sample script → 3 cues | Passed in isolated fake-provider browser test |
| Switch cues after editing | Saved text/title restored correctly |
| Saved draft changes | Old take marked stale; export blocked |
| Generate a new take and select it | Passed with fake provider; no additional real charge |
| Refresh after selecting | Same version and saved text restored |
| Keyboard | Dialog opens with focus; Escape closes it; standard form controls remain keyboard-accessible |
| Screenshots | Actual running UI, not mockups; desktop and mobile images visually inspected |
| Cover and flow diagrams | SVGs rendered in Chrome, bounds checked; three localized versions inspected |

The browser's initial screenshot capture produced a repeated mobile image; it was replaced by a fresh mobile viewport capture and inspected. Only the corrected image is included.

## Offline automated checks

`python -m unittest discover -v`: **10 tests passed**.

Coverage includes:

- identical submission token reuse;
- UNKNOWN blocking a new submission and task-ID attachment;
- restart recovery of an interrupted submission;
- snapshot mismatch preventing export;
- query failure, empty result, and download retry without generation;
- remote failure and authentication feedback;
- invalid lengths/speeds and missing credentials;
- cross-origin writes, host restrictions, configuration secrecy;
- rejection of private/non-HTTPS audio destinations;
- explicit confirmation before clearing an unknown submission.

`node --check static/app.js` also passed; this is supplementary, not the sole validation.

Optional browser regression test (uses a fake provider and a temporary database; **no paid calls**):

```bash
# In the activated project virtual environment
python -m pip install playwright
python -m playwright install chromium
python tests/browser_smoke.py
```

Alternatively set `CHROME_EXECUTABLE` to an existing Chrome binary. The test uses local port 8792. Its synthetic audio fixture only tests UI flow; real decoding was checked separately with the live MP3 above.

## Not verified / 未验证 / 未検証

- Windows and Linux on actual machines. Their startup commands are documented, but were not executed on those operating systems.
- All 17 voices, all supported languages, very long scripts, account limits, and `.ai` region generation.
- Large batches, heavy concurrency, multiuser hosting, or arbitrary third-party output formats.
- Perceptual quality or exact pronunciation across languages. Listen before delivery.

No GPU/local model performance claim is made. The tool does not implement voice cloning, concatenation, subtitle alignment, or ZIP import.

## Public-file checks

Three README language links, image links, examples, license, and local references were checked against the delivered files. Sponsor blocks use the supplied official logo and searchable translated text; neither reference preview image is embedded. Public source and assets were scanned against the configured key without printing its value. `.env`, the local database/audio, and virtual environment remain excluded from version control.
