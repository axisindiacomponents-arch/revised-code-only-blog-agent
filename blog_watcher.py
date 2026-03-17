"""
Axis India Blog Watcher
=======================
Watches a folder on your desktop for new .docx script files.
When a new file is detected, it automatically:
  1. Reads the video script from the .docx
  2. Fetches the Master Blog Guide from GitHub
  3. Calls Claude to write the blog
  4. Saves the HTML code, summary, and emailer to an Output folder

HOW TO RUN:
  python blog_watcher.py

HOW TO USE:
  Just drop any .docx script file into your "Axis Blog Scripts" folder.
  Check the "Axis Blog Scripts/Output" folder for the results.
"""

import os
import time
import requests
import anthropic
from pathlib import Path
from datetime import datetime
from docx import Document
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

# ─── CONFIGURATION ────────────────────────────────────────────────────────────

# Load API key from .env file (in the same folder as this script)
load_dotenv()

# Folder to watch — change this path if your Desktop is in a different location
WATCH_FOLDER = Path.home() / "Desktop" / "Axis Blog Scripts"

# Output folder — results will be saved here
OUTPUT_FOLDER = WATCH_FOLDER / "Output"

# GitHub raw URL for your Master Blog Guide
# Replace this with the actual raw URL of your doc in GitHub
# To get this: go to your file in GitHub → click Raw → copy the URL
GITHUB_MASTER_GUIDE_URL = "https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/Axis_Blog_Creation_Master_Guide.docx"

# Anthropic API key — loaded from .env file
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# ──────────────────────────────────────────────────────────────────────────────


def read_docx(file_path: Path) -> str:
    """Extract all text from a .docx file."""
    doc = Document(file_path)
    text = []
    for para in doc.paragraphs:
        if para.text.strip():
            text.append(para.text.strip())
    return "\n\n".join(text)


def fetch_master_guide() -> str:
    """
    Fetch the Master Blog Guide from GitHub.
    Returns the text content of the guide.
    """
    print("  → Fetching Master Blog Guide from GitHub...")

    # If the guide is a .docx on GitHub, we download it and extract text
    response = requests.get(GITHUB_MASTER_GUIDE_URL, timeout=30)
    response.raise_for_status()

    # Save temporarily to read it
    temp_path = Path("/tmp/master_guide.docx")
    temp_path.write_bytes(response.content)
    guide_text = read_docx(temp_path)
    temp_path.unlink()  # Clean up temp file

    print("  → Master guide fetched successfully.")
    return guide_text


def generate_blog(script_text: str, master_guide: str) -> dict:
    """
    Send the script and master guide to Claude and get back:
    - html_code: the full blog HTML
    - summary: 3-5 sentence blog summary
    - emailer: subject line + email copy
    """
    print("  → Sending to Claude for blog generation...")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""You are an expert blog writer for Axis India, a manufacturer of electrical hardware.

Below is the Master Blog Creation Guide that contains all the rules you must follow, followed by the video script to convert into a blog.

---
MASTER BLOG CREATION GUIDE:
{master_guide}

---
VIDEO SCRIPT:
{script_text}

---

Now create the blog following every rule in the Master Guide.

Your response must contain exactly three clearly labelled sections:

=== HTML CODE ===
[The complete blog as HTML code, ready to use directly]

=== BLOG SUMMARY ===
[3-5 plain-text sentences summarising the blog]

=== EMAILER COPY ===
[Subject line + 3-4 sentences promoting the blog]

=== HUMAN REVIEW FLAGS ===
[List anything that needs human attention — missing image URLs, unclear script sections, unverifiable specs. Write NONE if nothing to flag.]
"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = message.content[0].text

    # Parse the four sections from the response
    result = {
        "html_code": "",
        "summary": "",
        "emailer": "",
        "flags": ""
    }

    sections = {
        "html_code": ("=== HTML CODE ===", "=== BLOG SUMMARY ==="),
        "summary": ("=== BLOG SUMMARY ===", "=== EMAILER COPY ==="),
        "emailer": ("=== EMAILER COPY ===", "=== HUMAN REVIEW FLAGS ==="),
        "flags": ("=== HUMAN REVIEW FLAGS ===", None)
    }

    for key, (start_marker, end_marker) in sections.items():
        if start_marker in response_text:
            start = response_text.index(start_marker) + len(start_marker)
            if end_marker and end_marker in response_text:
                end = response_text.index(end_marker)
                result[key] = response_text[start:end].strip()
            else:
                result[key] = response_text[start:].strip()

    print("  → Blog generated successfully.")
    return result


def save_outputs(script_filename: str, blog_data: dict):
    """Save all three outputs as files in the Output folder."""

    # Create output folder if it doesn't exist
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    # Use the script filename (without extension) as the base name
    base_name = Path(script_filename).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_base = OUTPUT_FOLDER / f"{base_name}_{timestamp}"

    # 1. Save HTML code
    html_file = output_base.with_suffix(".html")
    html_file.write_text(blog_data["html_code"], encoding="utf-8")
    print(f"  → HTML saved:    {html_file.name}")

    # 2. Save summary + emailer + flags as a single text file
    notes_file = Path(str(output_base) + "_summary_emailer.txt")
    notes_content = f"""BLOG SUMMARY
============
{blog_data['summary']}


EMAILER COPY
============
{blog_data['emailer']}


HUMAN REVIEW FLAGS
==================
{blog_data['flags']}
"""
    notes_file.write_text(notes_content, encoding="utf-8")
    print(f"  → Summary & emailer saved: {notes_file.name}")


def process_script(file_path: Path):
    """Full pipeline for one script file."""

    print(f"\n{'='*60}")
    print(f"  New script detected: {file_path.name}")
    print(f"{'='*60}")

    # Small delay to ensure the file is fully written before we read it
    time.sleep(2)

    try:
        # Step 1: Read the script
        print("  → Reading script...")
        script_text = read_docx(file_path)

        if not script_text.strip():
            print("  ✗ Error: The script file appears to be empty.")
            return

        # Step 2: Fetch the master guide from GitHub
        master_guide = fetch_master_guide()

        # Step 3: Generate the blog
        blog_data = generate_blog(script_text, master_guide)

        # Step 4: Save the outputs
        save_outputs(file_path.name, blog_data)

        print(f"\n  ✓ Done! Check the Output folder inside Axis Blog Scripts.")
        print(f"{'='*60}\n")

    except requests.RequestException as e:
        print(f"  ✗ Could not fetch master guide from GitHub: {e}")
        print("  Check that GITHUB_MASTER_GUIDE_URL in the script is correct.")
    except anthropic.APIError as e:
        print(f"  ✗ Claude API error: {e}")
    except Exception as e:
        print(f"  ✗ Unexpected error: {e}")


# ─── FOLDER WATCHER ───────────────────────────────────────────────────────────

class ScriptFolderHandler(FileSystemEventHandler):
    """Watches the folder and triggers processing when a new .docx appears."""

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Only process .docx files, ignore temp files Word creates (start with ~$)
        if file_path.suffix.lower() == ".docx" and not file_path.name.startswith("~$"):
            process_script(file_path)


def start_watcher():
    """Start watching the folder."""

    # Create the watch folder if it doesn't exist yet
    WATCH_FOLDER.mkdir(parents=True, exist_ok=True)

    print("\n" + "="*60)
    print("  Axis India Blog Watcher — Running")
    print("="*60)
    print(f"  Watching folder: {WATCH_FOLDER}")
    print(f"  Outputs saved to: {OUTPUT_FOLDER}")
    print(f"\n  Drop a .docx script file into the folder above")
    print(f"  and the blog will be generated automatically.")
    print(f"\n  Press Ctrl+C to stop.")
    print("="*60 + "\n")

    # Check API key is present
    if not ANTHROPIC_API_KEY:
        print("  ✗ ERROR: ANTHROPIC_API_KEY not found.")
        print("  Create a .env file next to this script with:")
        print("  ANTHROPIC_API_KEY=your_key_here\n")
        return

    event_handler = ScriptFolderHandler()
    observer = Observer()
    observer.schedule(event_handler, str(WATCH_FOLDER), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n  Watcher stopped.")

    observer.join()


if __name__ == "__main__":
    start_watcher()
