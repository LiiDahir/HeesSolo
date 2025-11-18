from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
import yt_dlp
import os
import pathlib
import uvicorn
from spleeter.separator import Separator
import subprocess

app = FastAPI(title="🎵 AI Music Cleaner", version="2.2")

BASE_DIR = pathlib.Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "Downloads"
OUTPUT_DIR = BASE_DIR / "output"
DOWNLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Step 1: Download audio
def download_audio(youtube_url: str, file_name: str = "audio") -> str:
    output_path = DOWNLOAD_DIR / file_name
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',  # prefer m4a, fallback to best
        'outtmpl': str(output_path.with_suffix('')),
        'quiet': True,
        'noplaylist': True,  # ensure single video
        'ignoreerrors': True, # skip if some formats fail
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Download failed: {str(e)}")
    final_file = str(output_path) + ".mp3"    
    return final_file

# Step 2: Separate vocals/music
def separate_audio(file_path: str) -> str:
    song_name = pathlib.Path(file_path).stem
    song_output = OUTPUT_DIR / song_name
    song_output.mkdir(exist_ok=True)
    try:
        separator = Separator('spleeter:2stems')
        separator.separate_to_file(file_path, str(OUTPUT_DIR))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Separation failed: {str(e)}")
    return str(song_output)

# Step 3: Keep only audible parts
def keep_only_sound(input_file: str) -> str:
    output_file = pathlib.Path(input_file).with_name(pathlib.Path(input_file).stem + "_sound.wav")
    cmd = [
        "ffmpeg", "-y", "-i", input_file,
        "-af", "silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.1:stop_periods=-1:stop_threshold=-40dB:stop_silence=0.1",
        str(output_file)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return str(output_file)

# Web UI
@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <html>
    <head>
        <title>🎧 AI Music Cleaner</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
    </head>
    <body class="bg-light">
        <div class="container mt-5 text-center">
            <h2 class="mb-4">🎶 AI Music Cleaner</h2>
            <p class="text-muted">Extract only the sound parts (no silence) from any YouTube song!</p>
            <div class="card p-4 shadow-sm">
                <input id="url" type="text" class="form-control" placeholder="🎥 Paste YouTube link">
                <input id="name" type="text" class="form-control mt-3" placeholder="📁 Optional file name">
                <select id="type" class="form-select mt-3">
                    <option value="vocals">🎤 Vocals</option>
                    <option value="music">🎸 Instrumental</option>
                </select>
                <button class="btn btn-primary mt-3 w-100" onclick="process()">Clean Music</button>
            </div>
            <div id="result" class="mt-5"></div>
        </div>

        <script>
        async function process() {
            const url = document.getElementById('url').value;
            const name = document.getElementById('name').value || 'audio';
            const type = document.getElementById('type').value;

            if (!url) {
                document.getElementById('result').innerHTML = '<p class="text-danger">⚠️ Please enter a YouTube link.</p>';
                return;
            }

            document.getElementById('result').innerHTML = '<p>Processing... please wait ⏳</p>';

            const res = await fetch(`/process?youtube_url=${encodeURIComponent(url)}&file_name=${encodeURIComponent(name)}&file_type=${encodeURIComponent(type)}`);
            const data = await res.json();

            if (data.error) {
                document.getElementById('result').innerHTML = `<p class="text-danger">❌ ${data.error}</p>`;
                return;
            }

            document.getElementById('result').innerHTML = `
                <div class="card p-3 shadow-sm">
                    <h5>✅ Download Ready</h5>
                    <a href="${data.file}" class="btn btn-success mt-2" download>Download ${type}.wav</a>
                </div>
            `;
        }
        </script>
    </body>
    </html>
    """

# API endpoint
@app.get("/process")
def process_audio(
    youtube_url: str = Query(...),
    file_name: str = Query("audio"),
    file_type: str = Query("vocals")
):
    if file_type not in ["vocals", "music"]:
        return JSONResponse(status_code=400, content={"error": "file_type must be 'vocals' or 'music'"})
    try:
        file_path = download_audio(youtube_url, file_name)
        out_dir = separate_audio(file_path)
        selected_file = os.path.join(out_dir, "vocals.wav") if file_type=="vocals" else os.path.join(out_dir, "accompaniment.wav")
        sound_file = keep_only_sound(selected_file)
        final_path = OUTPUT_DIR / (pathlib.Path(file_name).stem + "_sound.wav")
        os.replace(sound_file, final_path)
        return {"file": f"/file?v={final_path}"}
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"error": e.detail})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# Serve files
@app.get("/file")
def get_file(v: str):
    if not os.path.exists(v):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(v, media_type="audio/wav")

# Run
if __name__ == "__main__":
    print("🚀 Starting AI Music Cleaner on http://127.0.0.1:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
