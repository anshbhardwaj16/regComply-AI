"""Build the submission assets: deck PDF, slide PNGs, live demo recording, narrated MP4.

Usage (from repo root):
    .venv\\Scripts\\python deck\\build.py slides   # PDF + slide PNGs
    .venv\\Scripts\\python deck\\build.py demo     # record the real app (full results need an LLM key in .env)
    .venv\\Scripts\\python deck\\build.py video    # narrate + assemble MP4
    .venv\\Scripts\\python deck\\build.py all

Narration uses OpenAI gpt-4o-mini-tts when OPENAI_API_KEY is set (NARRATOR=windows forces the offline
Windows voice named by NARRATOR_VOICE, default "Microsoft David Desktop").
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import wave
from pathlib import Path

import imageio_ffmpeg
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DECK = ROOT / "deck" / "submission-deck.html"
OUT = ROOT / "deck" / "out"
SLIDES = OUT / "slides"
DEMO = OUT / "demo"
WORK = OUT / "work"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H = 1280, 720
VW, VH, FPS = 1920, 1080, 30
PORT = 8765
APP_URL = f"http://127.0.0.1:{PORT}"
VOICE = os.getenv("NARRATOR_VOICE", "Microsoft David Desktop")
FONT = "C\\:/Windows/Fonts/segoeuib.ttf"


def launch(p):
    return p.chromium.launch(channel="chrome", headless=True)


# ── Slides ────────────────────────────────────────────────────────────────────

def build_slides():
    SLIDES.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
        page.goto(DECK.as_uri(), wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        count = page.locator(".slide").count()
        heights = page.evaluate("""() => [...document.querySelectorAll('.slide')].map(
            s => Math.round(s.getBoundingClientRect().height))""")
        too_tall = [(i + 1, h) for i, h in enumerate(heights) if h > H]
        for n, h in too_tall:
            print(f"slide {n:2d}: {h}px tall  <-- OVERFLOW")
        if not too_tall:
            print("all slides fit 1280x720")

        page.evaluate("document.body.classList.add('single')")
        for i in range(count):
            page.evaluate(f"""() => document.querySelectorAll('.slide').forEach(
                (s, j) => s.classList.toggle('show', j === {i}))""")
            page.screenshot(path=str(SLIDES / f"slide-{i + 1:02d}.png"))
        page.evaluate("document.body.classList.remove('single')")

        page.emulate_media(media="print")
        page.pdf(path=str(OUT / "regComply-AI-pitch-deck.pdf"), width=f"{W}px", height=f"{H}px",
                 print_background=True, margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
        browser.close()
    print(f"{count} slides -> {SLIDES}")
    print(f"PDF -> {OUT / 'regComply-AI-pitch-deck.pdf'}")


# ── Demo recording ────────────────────────────────────────────────────────────

def has_llm_key():
    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    provider = (env.get("LLM_PROVIDER") or "groq").lower()
    key_name = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}.get(provider, "GROQ_API_KEY")
    key = env.get(key_name) or ""
    return bool(key.strip()) and "your" not in key.lower()


def start_server():
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{APP_URL}/health", timeout=1)
            return proc
        except OSError:
            time.sleep(0.5)
    proc.kill()
    raise RuntimeError("backend did not start on port %d" % PORT)


def smooth_scroll(page, selector, offset=90):
    page.evaluate(f"""() => {{
        const el = document.querySelector({json.dumps(selector)});
        if (el) window.scrollTo({{top: el.getBoundingClientRect().top + window.scrollY - {offset}, behavior: 'smooth'}});
    }}""")


def record_demo():
    live = has_llm_key()
    if DEMO.exists():
        shutil.rmtree(DEMO)
    DEMO.mkdir(parents=True)
    server = start_server()
    events, data = [], {"mode": "live" if live else "ui-only"}
    errors = []
    try:
        with sync_playwright() as p:
            browser = launch(p)
            ctx = browser.new_context(viewport={"width": W, "height": H},
                                      record_video_dir=str(DEMO), record_video_size={"width": W, "height": H})
            page = ctx.new_page()
            t0 = time.monotonic()
            page.on("dialog", lambda d: (errors.append(d.message), d.dismiss()))

            def mark(name):
                events.append({"name": name, "t": round(time.monotonic() - t0, 2)})
                print(f"  {events[-1]['t']:7.2f}s  {name}")

            page.goto(APP_URL, wait_until="networkidle")
            # Magenta flash lets build_video() measure the offset between this clock and the video timeline.
            page.evaluate("""() => { const d = document.createElement('div'); d.id = '__sync';
                d.style.cssText = 'position:fixed;inset:0;background:#ff00ff;z-index:99999';
                document.body.appendChild(d); }""")
            mark("sync")
            page.wait_for_timeout(600)
            page.evaluate("document.getElementById('__sync').remove()")
            page.wait_for_timeout(700)
            mark("home")
            page.wait_for_timeout(2500)
            page.click("button[onclick='loadSampleData()']")
            mark("sample")
            page.wait_for_timeout(1200)
            page.evaluate("document.getElementById('reg-text').scrollTo({top: 400, behavior: 'smooth'})")
            page.wait_for_timeout(1500)
            page.evaluate("document.getElementById('ctl-text').scrollTo({top: 400, behavior: 'smooth'})")
            page.wait_for_timeout(1500)
            smooth_scroll(page, "#analyze-btn", 400)
            page.wait_for_timeout(1500)

            if live:
                page.click("#analyze-btn")
                mark("run")
                page.wait_for_selector("#results-section:not(.hidden)", timeout=420_000)
                mark("results")
                data["analysis"] = page.evaluate("analysisData")
                page.wait_for_timeout(5000)
                smooth_scroll(page, ".tabs", 70)  # clear the app's sticky mode bar
                page.wait_for_timeout(1500)
                mark("trace")
                headers = page.locator("#traceability-list .trace-header")
                refresh = headers.filter(has_text="2 years")
                (refresh if refresh.count() else headers).first.click()
                page.wait_for_timeout(5500)
                for tab in ("gaps", "remediation", "controls"):
                    page.click(f"[onclick=\"showTab('{tab}', this)\"]")
                    mark(tab)
                    smooth_scroll(page, ".tabs", 70)
                    page.wait_for_timeout(5000)

                page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
                page.wait_for_timeout(800)
                page.click("button[onclick='openSimulator()']")
                mark("sim_open")
                page.wait_for_timeout(1500)
                page.locator(".example-chip").first.click()
                page.wait_for_timeout(1200)
                with page.expect_response("**/api/simulate", timeout=300_000) as resp:
                    mark("sim_run")
                    page.click("#sim-btn")
                data["simulation"] = resp.value.json()
                page.wait_for_selector("#sim-results:not(.hidden)", timeout=30_000)
                mark("sim_done")
                page.wait_for_timeout(3000)
                page.evaluate("document.querySelector('.modal').scrollTo({top: 99999, behavior: 'smooth'})")
                page.wait_for_timeout(4000)
                page.click(".modal-close")

            page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
            page.wait_for_timeout(800)
            page.click("#mode-change")
            mark("change_mode")
            page.wait_for_timeout(1500)
            page.click("button[onclick='loadChangeSample()']")
            page.wait_for_timeout(3000)
            if live:
                with page.expect_response("**/api/change-analysis", timeout=300_000) as resp:
                    mark("change_run")
                    page.click("#change-analyze-btn")
                data["change"] = resp.value.json()
                page.wait_for_selector("#change-results:not(.hidden)", timeout=30_000)
                mark("change_done")
                page.wait_for_timeout(1500)
                smooth_scroll(page, "#change-results")
                page.wait_for_timeout(3500)
                smooth_scroll(page, "#changes-list")
                page.wait_for_timeout(4500)
            else:
                smooth_scroll(page, "#change-analyze-btn", 400)
                page.wait_for_timeout(3000)
            mark("end")
            video_path = page.video.path()
            ctx.close()
            browser.close()
        shutil.move(video_path, DEMO / "demo.webm")
    finally:
        server.kill()
    data["events"] = events
    data["errors"] = errors
    (DEMO / "demo.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"demo ({data['mode']}) -> {DEMO / 'demo.webm'}")
    if errors:
        print("app alerts during demo:", errors)


# ── Narration script ──────────────────────────────────────────────────────────

def slide(n, text):
    return {"kind": "slide", "img": SLIDES / f"slide-{n:02d}.png", "text": text}


def beat(start, end, text, label, guard=0.8):
    """guard: seconds cut before the end event, so the next action's scroll/close isn't the held frame."""
    return {"kind": "demo", "start": start, "end": end, "text": text, "label": label, "guard": guard}


def num(x):
    return f"{x:g}" if isinstance(x, (int, float)) else str(x)


def script(demo):
    intro = [
        slide(1, "This is RegComply AI, an agentic regulatory intelligence platform for banks, built for "
                 "problem statement one of the ET AI Hackathon."),
        slide(3, "Banks paid over three hundred billion dollars in fines between 2008 and 2016. Mapping obligations "
                 "to controls is still manual, so gaps surface at audit time, and every amendment restarts the work."),
        slide(5, "Seven specialised agents do the work. They extract obligations and controls, map each obligation "
                 "to its best control with a confidence score, risk-score the gaps, and write a remediation plan and "
                 "a board summary. Two more agents handle regulatory change and what-if simulation."),
    ]
    outro = [
        slide(8, "We fully cover eleven of the fourteen listed features, and evidence-based assessment partially, "
                 "so we claim F3, D2: structured text input, with schema-constrained prompts, explicit parameter "
                 "checks, and confidence scores."),
        slide(9, "For banks, that means a faster first pass, gaps found before an inspection finds them, and early "
                 "sight of a proposed rule's impact."),
        slide(10, "Every finding is traceable and explained, the score is computed in code, and compliance officers "
                  "make the final call."),
        slide(12, "RegComply AI. Regulations to remediation, in one agentic run. Thank you."),
    ]

    beats = [beat("home", "run" if demo["mode"] == "live" else "change_mode",
                  "Let's run it live on the built-in sample: the RBI KYC master direction, and a bank policy with "
                  "eight controls.", "LIVE DEMO  ·  Inputs")]
    if demo["mode"] == "live":
        a = demo["analysis"]
        times = {e["name"]: e["t"] for e in demo["events"]}
        runtime = round(times["results"] - times["run"])
        gaps = sorted(a["gaps"], key=lambda g: g.get("risk_score", 0), reverse=True)
        critical = sum(1 for g in gaps if g.get("risk_level") == "Critical")
        sim = demo.get("simulation", {})
        chg = demo.get("change", {})
        coverage = {m["obligation_id"]: m.get("coverage") for m in a["mappings"]}
        caught_refresh = any("every 2 years" in o["text"] and coverage.get(o["id"]) in ("Partial", "None")
                             for o in a["obligations"])
        trace_line = "Traceability links each obligation to its clause, matched control, confidence, gap and fix." + (
            " Here, it caught that the bank refreshes high-risk KYC every three years, where the regulation requires "
            "two." if caught_refresh else "")
        gap_line = (f"{len(gaps)} gaps, ranked by risk, {critical} of them critical. The top risk, scored "
                    f"{gaps[0]['risk_score']} out of 100, is clause {gaps[0].get('regulation_ref', '')}: "
                    f"{gaps[0]['obligation_text']}" if gaps else "No gaps were found.")
        delta = sim.get("score_delta", 0)
        delta_words = f"{'down' if delta < 0 else 'up'} {num(abs(delta))} points" if isinstance(delta, (int, float)) \
            else "a change"
        beats += [
            beat("run", "results", "One click starts the pipeline, and each agent reports progress as it finishes.",
                 "LIVE DEMO  ·  Agent pipeline"),
            beat("results", "trace",
                 f"Done in about {runtime} seconds. {a['total_obligations']} obligations: {a['fully_covered']} fully "
                 f"covered, {a['partially_covered']} partially, {a['not_covered']} not at all. A score of "
                 f"{num(a['compliance_score'])} percent.", "LIVE DEMO  ·  Results", guard=2.2),
            beat("trace", "gaps", trace_line, "LIVE DEMO  ·  Traceability"),
            beat("gaps", "remediation", gap_line, "LIVE DEMO  ·  Gap register"),
            beat("remediation", "controls", "Each gap gets an action, an owner, a timeline and an effort estimate.",
                 "LIVE DEMO  ·  Remediation"),
            beat("controls", "sim_open", "Controls are scored for effectiveness, type and automation.",
                 "LIVE DEMO  ·  Controls", guard=2.0),
            beat("sim_open", "sim_done", "What if RBI cut the high-risk KYC refresh to six months?",
                 "LIVE DEMO  ·  What-if simulation"),
            beat("sim_done", "change_mode",
                 f"The simulator projects a score of {num(sim.get('new_compliance_score', '?'))} percent, "
                 f"{delta_words}, and lists the new gaps and the actions required.",
                 "LIVE DEMO  ·  What-if simulation", guard=1.4),
            beat("change_mode", "change_done", "Finally, change intelligence: comparing the 2022 and 2024 versions.",
                 "LIVE DEMO  ·  Change intelligence"),
            beat("change_done", "end",
                 f"The agent found {chg.get('total_changes', 'several')} changes, {chg.get('critical_changes', 0)} "
                 f"critical, each with an action and a timeline.", "LIVE DEMO  ·  Change intelligence"),
        ]
    else:
        beats.append(beat("change_mode", "end",
                          "The change intelligence view takes two versions of the same regulation. Here we load the "
                          "2022 and 2024 versions of the sample direction.", "LIVE DEMO  ·  Change intelligence"))
    return intro + beats + outro


# ── Video assembly ────────────────────────────────────────────────────────────

def ffmpeg(*args):
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *map(str, args)], check=True)


WINDOWS_SPOKEN = {"RegComply AI": "RegComply AI", "RBI": "RBI", "KYC": "KYC", "ET AI": "E T A I",
                  "F3, D2": "F 3, D 2"}
NARRATOR_STYLE = ("Professional product-demo narrator for a banking technology pitch. Clear and confident, "
                  "with a brisk, energetic pace and no long pauses; warm but not salesy. "
                  "Read acronyms like RBI and KYC letter by letter.")


def synthesize(segments):
    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    use_openai = env.get("OPENAI_API_KEY") and env.get("NARRATOR", "openai") == "openai"
    for i, seg in enumerate(segments):
        seg["wav"] = WORK / f"n{i:02d}.wav"
    if use_openai:
        synthesize_openai(segments, env["OPENAI_API_KEY"], env.get("NARRATOR_VOICE_OPENAI", "ash"))
    else:
        synthesize_windows(segments)
    for seg in segments:
        with wave.open(str(seg["wav"])) as w:
            seg["speech"] = w.getnframes() / w.getframerate()


def synthesize_openai(segments, api_key, voice):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    for seg in segments:
        pcm = client.audio.speech.create(model="gpt-4o-mini-tts", voice=voice, input=seg["text"],
                                         instructions=NARRATOR_STYLE, response_format="pcm").content
        with wave.open(str(seg["wav"]), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(pcm)


def synthesize_windows(segments):
    jobs = []
    for i, seg in enumerate(segments):
        txt = WORK / f"n{i:02d}.txt"
        spoken = seg["text"]
        for written, said in WINDOWS_SPOKEN.items():
            spoken = spoken.replace(written, said)
        txt.write_text(spoken, encoding="utf-8")
        jobs.append({"txt": str(txt), "wav": str(seg["wav"])})
    (WORK / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
    ps = WORK / "tts.ps1"
    ps.write_text(f"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('{VOICE}')
$s.Rate = 0
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(44100, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($j in (Get-Content -Raw '{WORK / "jobs.json"}' | ConvertFrom-Json)) {{
  $s.SetOutputToWaveFile($j.wav, $fmt)
  $s.Speak([IO.File]::ReadAllText($j.txt))
}}
$s.Dispose()
""", encoding="utf-8")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps)], check=True)


AUDIO_CHAIN = "adelay=delays=350:all=1,apad,aformat=sample_rates=44100:channel_layouts=stereo"
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", FPS,
       "-c:a", "aac", "-b:a", "160k"]


def slide_clip(seg, out):
    dur = seg["speech"] + 1.2
    vf = (f"[0:v]scale={VW}:{VH}:flags=lanczos,format=yuv420p,"
          f"fade=t=in:st=0:d=0.35,fade=t=out:st={dur - 0.35:.2f}:d=0.35[v];[1:a]{AUDIO_CHAIN}[a]")
    ffmpeg("-loop", 1, "-framerate", FPS, "-t", f"{dur:.2f}", "-i", seg["img"], "-i", seg["wav"],
           "-filter_complex", vf, "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", *ENC, out)
    return dur


def demo_clip(seg, times, out):
    start, end = times[seg["start"]], times[seg["end"]] - seg["guard"]
    natural = max(end - start, 0.5)
    target = seg["speech"] + 1.0
    speed = natural / target if natural > target else 1.0
    label = seg["label"] + (f"   (sped up {speed:.0f}x)" if speed >= 1.5 else "")
    # Playwright only emits frames on screen changes; force CFR, then hold the last frame past the cut point.
    vf = (f"[0:v]setpts=(PTS-STARTPTS)/{speed:.4f},fps={FPS},tpad=stop_mode=clone:stop_duration={target + 5:.2f},"
          f"scale={VW}:{VH}:flags=lanczos,format=yuv420p,"
          f"drawtext=fontfile='{FONT}':text='{label}':x=36:y=h-th-36:fontsize=30:fontcolor=white:"
          f"box=1:boxcolor=0x0B1A35@0.85:boxborderw=14[v];[1:a]{AUDIO_CHAIN}[a]")
    ffmpeg("-ss", f"{start:.2f}", "-t", f"{natural:.2f}", "-i", DEMO / "demo.webm", "-i", seg["wav"],
           "-filter_complex", vf, "-map", "[v]", "-map", "[a]", "-t", f"{target:.2f}", *ENC, out)
    return target


def video_offset(sync_t):
    start = max(sync_t - 3, 0)
    raw = subprocess.run([FFMPEG, "-loglevel", "error", "-ss", f"{start:.2f}", "-t", "8", "-i", DEMO / "demo.webm",
                          "-vf", "fps=50,scale=16:9", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    size = 16 * 9 * 3
    for i in range(len(raw) // size):
        px = raw[i * size:(i + 1) * size]
        r, g, b = (sum(px[k::3]) / (16 * 9) for k in range(3))
        if r > 200 and g < 80 and b > 200:
            return start + i / 50 - sync_t
    raise RuntimeError("sync flash not found in demo recording")


def build_video():
    demo = json.loads((DEMO / "demo.json").read_text(encoding="utf-8"))
    times = {e["name"]: e["t"] for e in demo["events"]}
    offset = video_offset(times["sync"])
    print(f"  video offset {offset:+.2f}s")
    times = {name: t + offset for name, t in times.items()}
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    segments = script(demo)
    synthesize(segments)
    total, clips = 0.0, []
    for i, seg in enumerate(segments):
        out = WORK / f"c{i:02d}.mp4"
        total += slide_clip(seg, out) if seg["kind"] == "slide" else demo_clip(seg, times, out)
        clips.append(out)
        print(f"  clip {i:02d} {seg['kind']:5s} {total:6.1f}s")
    (WORK / "list.txt").write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    final = OUT / "regComply-AI-demo.mp4"
    ffmpeg("-f", "concat", "-safe", 0, "-i", WORK / "list.txt", "-c", "copy", "-movflags", "+faststart", final)
    (OUT / "narration.txt").write_text("\n\n".join(s["text"] for s in segments), encoding="utf-8")
    print(f"video ({demo['mode']}, {total / 60:.1f} min) -> {final}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("slides", "all"):
        build_slides()
    if cmd in ("demo", "all"):
        record_demo()
    if cmd in ("video", "all"):
        build_video()
